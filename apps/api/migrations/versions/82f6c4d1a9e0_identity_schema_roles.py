"""Move identity and business data into separately granted schemas.

Revision ID: 82f6c4d1a9e0
Revises: 6fd3a81b29c4
"""

from collections.abc import Sequence

from alembic import op

revision: str = "82f6c4d1a9e0"
down_revision: str | None = "6fd3a81b29c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTITY_TABLES = (
    "audit_events", "login_failures", "organization_config_commands",
    "organization_memberships", "organizations", "user_sessions", "users",
)
BUSINESS_TABLES = (
    "ai_analyses", "audit_cases", "audit_configurations", "audit_findings",
    "audit_rules", "audit_runs", "business_audit_events", "case_comments",
    "finding_evidence", "import_batches", "import_rows", "jobs",
    "outbox_events", "purchases", "suppliers",
)


def database_name() -> str:
    """Quote the current database for database-scoped search paths."""
    connection = op.get_bind()
    name = connection.engine.url.database
    assert name is not None
    return connection.dialect.identifier_preparer.quote(name)


def upgrade() -> None:
    # A short lock budget prevents a busy production database from stalling rollout.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("CREATE SCHEMA identity")
    op.execute("CREATE SCHEMA business")
    # Roles are cluster-wide. A separate test database may already have created them.
    for role in ("processmind_identity", "processmind_business"):
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '"
            + role + "') THEN CREATE ROLE " + role + " NOLOGIN; END IF; END $$"
        )
    for table in IDENTITY_TABLES:
        op.execute(f"ALTER TABLE public.{table} SET SCHEMA identity")
    for table in BUSINESS_TABLES:
        op.execute(f"ALTER TABLE public.{table} SET SCHEMA business")
    op.execute(
        "ALTER FUNCTION public.prevent_identity_physical_delete() SET SCHEMA identity"
    )
    for schema, role in (
        ("identity", "processmind_identity"),
        ("business", "processmind_business"),
    ):
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {role}"
        )
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}")
        op.execute(
            f"ALTER ROLE {role} IN DATABASE {database_name()} "
            f"SET search_path = {schema}, public"
        )
    # Administrative maintenance can resolve both owners without giving either
    # runtime role access to the other's schema. New migrations must name schemas.
    op.execute(f"ALTER DATABASE {database_name()} SET search_path = public, business, identity")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in BUSINESS_TABLES:
        op.execute(f"ALTER TABLE business.{table} SET SCHEMA public")
    for table in IDENTITY_TABLES:
        op.execute(f"ALTER TABLE identity.{table} SET SCHEMA public")
    op.execute(
        "ALTER FUNCTION identity.prevent_identity_physical_delete() SET SCHEMA public"
    )
    for schema, role in (
        ("identity", "processmind_identity"),
        ("business", "processmind_business"),
    ):
        op.execute(f"REVOKE ALL ON SCHEMA {schema} FROM {role}")
        op.execute(f"ALTER ROLE {role} IN DATABASE {database_name()} RESET search_path")
        op.execute(f"DROP SCHEMA {schema}")
    # Cluster-wide roles may still be used by another database; keep them unprivileged here.
    op.execute(f"ALTER DATABASE {database_name()} RESET search_path")
