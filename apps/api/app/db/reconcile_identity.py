"""Read-only audit of business references to identity-owned records."""

import json
from dataclasses import asdict, dataclass

from sqlalchemy import MetaData, Table, and_, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine

# Keep this inventory explicit: new tenant tables require a reviewed reference policy.
BUSINESS_TENANT_TABLES = (
    "ai_analyses",
    "audit_cases",
    "audit_configurations",
    "audit_findings",
    "audit_runs",
    "business_audit_events",
    "case_comments",
    "finding_evidence",
    "import_batches",
    "import_rows",
    "jobs",
    "outbox_events",
    "purchases",
    "suppliers",
)
IDENTITY_TENANT_TABLES = frozenset({"audit_events", "organization_memberships"})


@dataclass(frozen=True)
class Reference:
    source: str
    column: str
    target: str
    optional: bool = False
    same_tenant: bool = False


@dataclass(frozen=True)
class CheckResult:
    source: str
    column: str
    target: str
    checked_rows: int
    missing: int
    wrong_tenant: int


def references() -> tuple[Reference, ...]:
    """Declare every identity reference retained by the business schema."""
    tenant = tuple(
        Reference(table, "organization_id", "organizations")
        for table in BUSINESS_TENANT_TABLES
    )
    actors = (
        Reference("import_batches", "uploader_id", "users"),
        Reference("audit_runs", "requester_id", "users"),
        Reference("ai_analyses", "requester_id", "users"),
        Reference("business_audit_events", "actor_user_id", "users", optional=True),
    )
    members = (
        Reference(
            "audit_cases", "assignee_membership_id", "organization_memberships",
            optional=True, same_tenant=True,
        ),
        Reference(
            "case_comments", "author_membership_id", "organization_memberships",
            same_tenant=True,
        ),
    )
    return tenant + actors + members


def collect_report(connection: Connection) -> dict[str, object]:
    """Count missing and cross-tenant references in one caller-owned transaction."""
    observed = set(
        connection.scalars(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND column_name = 'organization_id'"
            )
        ).all()
    )
    expected = set(BUSINESS_TENANT_TABLES) | IDENTITY_TENANT_TABLES
    schema_errors = [f"unclassified_tenant_table:{name}" for name in sorted(observed - expected)]
    schema_errors += [f"missing_tenant_table:{name}" for name in sorted(expected - observed)]

    metadata = MetaData()
    available_tables = set(inspect(connection).get_table_names())
    table_names = {ref.source for ref in references()} | {ref.target for ref in references()}
    schema_errors += [f"missing_table:{name}" for name in sorted(table_names - available_tables)]
    if schema_errors:
        return {"status": "inconsistent", "schema_errors": schema_errors, "checks": []}

    tables = {name: Table(name, metadata, autoload_with=connection) for name in table_names}
    checks: list[CheckResult] = []
    for ref in references():
        source, target = tables[ref.source], tables[ref.target]
        if ref.column not in source.c or "id" not in target.c:
            schema_errors.append(f"missing_reference_column:{ref.source}.{ref.column}")
            continue
        if ref.same_tenant and "organization_id" not in target.c:
            schema_errors.append(f"missing_tenant_column:{ref.target}")
            continue

        source_id = source.c[ref.column]
        target_id = target.c.id
        present = source_id.is_not(None)
        checked_query = select(func.count()).select_from(source)
        if ref.optional:
            checked_query = checked_query.where(present)
        checked = connection.scalar(checked_query)
        # A left join distinguishes an absent target from an inactive historical record.
        missing_filter = and_(present, target_id.is_(None)) if ref.optional else target_id.is_(None)
        missing = connection.scalar(
            select(func.count())
            .select_from(source.outerjoin(target, source_id == target_id))
            .where(missing_filter)
        )
        wrong_tenant = 0
        if ref.same_tenant:
            wrong_tenant = int(
                connection.scalar(
                    select(func.count())
                    .select_from(source.join(target, source_id == target_id))
                    .where(source.c.organization_id != target.c.organization_id)
                )
                or 0
            )
        checks.append(
            CheckResult(
                ref.source, ref.column, ref.target,
                int(checked or 0), int(missing or 0), wrong_tenant,
            )
        )

    inconsistent = bool(schema_errors) or any(item.missing or item.wrong_tenant for item in checks)
    return {
        "status": "inconsistent" if inconsistent else "clean",
        "schema_errors": schema_errors,
        "checks": [asdict(item) for item in checks],
    }


def open_engine() -> Engine:
    """Load database settings only inside the guarded CLI boundary."""
    from app.db.engine import make_engine

    return make_engine()


def main() -> int:
    """Print a safe machine-readable report and fail closed on technical errors."""
    try:
        with open_engine().connect() as connection:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            report = collect_report(connection)
            connection.rollback()
    except Exception:
        # Do not print the exception: driver messages can contain connection details.
        print(json.dumps({"status": "error", "reason": "database_or_schema_unavailable"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "clean" else 2


if __name__ == "__main__":
    raise SystemExit(main())
