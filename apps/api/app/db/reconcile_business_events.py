"""Reconcile the owned business trail with the temporary identity-owned mirror."""

import argparse
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.engine import make_engine

BUSINESS_ACTION_FILTER = """(
    legacy.action LIKE 'import.%' OR legacy.action LIKE 'audit.%' OR legacy.action LIKE 'ai.%'
    OR legacy.action LIKE 'finding.%' OR legacy.action LIKE 'case.%'
)"""


def collect_report(connection: Connection) -> dict[str, int | str]:
    """Count missing and conflicting copies without exposing event contents."""
    owned_only = connection.scalar(text("""
        SELECT count(*) FROM business_audit_events AS owned
        LEFT JOIN audit_events AS legacy ON legacy.id = owned.id
        WHERE legacy.id IS NULL
    """))
    legacy_only = connection.scalar(text(f"""
        SELECT count(*) FROM audit_events AS legacy
        LEFT JOIN business_audit_events AS owned ON owned.id = legacy.id
        WHERE {BUSINESS_ACTION_FILTER}
          AND owned.id IS NULL
    """))
    conflicts = connection.scalar(text("""
        SELECT count(*) FROM business_audit_events AS owned
        JOIN audit_events AS legacy ON legacy.id = owned.id
        WHERE ROW(owned.organization_id, owned.actor_user_id, owned.action,
                  owned.subject_type, owned.subject_id, owned.metadata_json,
                  owned.correlation_id, owned.occurred_at)
              IS DISTINCT FROM
              ROW(legacy.organization_id, legacy.actor_user_id, legacy.action,
                  legacy.subject_type, legacy.subject_id, legacy.metadata_json,
                  legacy.correlation_id, legacy.occurred_at)
    """))
    return {
        "status": "clean" if not legacy_only and not conflicts else "inconsistent",
        "owned_only": int(owned_only or 0),
        "legacy_only": int(legacy_only or 0),
        "conflicts": int(conflicts or 0),
    }


def restore_legacy_copy(connection: Connection) -> int:
    """Restore only absent mirror rows after writers have been stopped for rollback."""
    report = collect_report(connection)
    if report["status"] != "clean":
        raise ValueError("business event copies require investigation before restore")
    result = connection.execute(text("""
        INSERT INTO audit_events (
            id, organization_id, actor_user_id, action, subject_type, subject_id,
            metadata_json, correlation_id, occurred_at
        )
        SELECT owned.id, owned.organization_id, owned.actor_user_id, owned.action,
               owned.subject_type, owned.subject_id, owned.metadata_json,
               owned.correlation_id, owned.occurred_at
        FROM business_audit_events AS owned
        LEFT JOIN audit_events AS legacy ON legacy.id = owned.id
        WHERE legacy.id IS NULL
        ON CONFLICT (id) DO NOTHING
    """))
    return result.rowcount


def main() -> int:
    """Run a read-only check or an explicitly requested rollback copy."""
    parser = argparse.ArgumentParser(description="Reconcile business event copies")
    parser.add_argument("--restore-legacy", action="store_true")
    args = parser.parse_args()
    try:
        with make_engine().connect() as connection:
            if args.restore_legacy:
                # The operator stops all event writers before this rollback command.
                with connection.begin():
                    restored = restore_legacy_copy(connection)
                report = collect_report(connection)
                report["restored"] = restored
            else:
                connection.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
                report = collect_report(connection)
                connection.rollback()
    except Exception:
        # Connection and constraint details can include private infrastructure names.
        print(json.dumps({"status": "error", "reason": "database_or_event_copy_unavailable"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "clean" else 2


if __name__ == "__main__":
    raise SystemExit(main())
