"""Detach business references from identity-owned tables.

Revision ID: 6fd3a81b29c4
Revises: 9b6d2f41a8c3
"""

from collections.abc import Sequence

from alembic import op

revision: str = "6fd3a81b29c4"
down_revision: str | None = "9b6d2f41a8c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Keep this inventory explicit so a downgrade recreates the same validated links.
IDENTITY_REFERENCES = (
    (
        "import_batches_organization_id_fkey",
        "import_batches",
        "organizations",
        ("organization_id",),
        ("id",),
    ),
    ("import_batches_uploader_id_fkey", "import_batches", "users", ("uploader_id",), ("id",)),
    ("jobs_organization_id_fkey", "jobs", "organizations", ("organization_id",), ("id",)),
    ("suppliers_organization_id_fkey", "suppliers", "organizations", ("organization_id",), ("id",)),
    (
        "audit_runs_organization_id_fkey",
        "audit_runs",
        "organizations",
        ("organization_id",),
        ("id",),
    ),
    ("audit_runs_requester_id_fkey", "audit_runs", "users", ("requester_id",), ("id",)),
    (
        "ai_analyses_organization_id_fkey",
        "ai_analyses",
        "organizations",
        ("organization_id",),
        ("id",),
    ),
    ("ai_analyses_requester_id_fkey", "ai_analyses", "users", ("requester_id",), ("id",)),
    (
        "audit_cases_organization_id_assignee_membership_id_fkey",
        "audit_cases",
        "organization_memberships",
        ("organization_id", "assignee_membership_id"),
        ("organization_id", "id"),
    ),
    (
        "case_comments_organization_id_author_membership_id_fkey",
        "case_comments",
        "organization_memberships",
        ("organization_id", "author_membership_id"),
        ("organization_id", "id"),
    ),
    (
        "outbox_events_organization_id_fkey",
        "outbox_events",
        "organizations",
        ("organization_id",),
        ("id",),
    ),
)

IDENTITY_TABLES = ("organizations", "users", "organization_memberships")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Historical UUIDs must remain resolvable after their cross-domain FKs go away.
    op.execute(
        """
        CREATE FUNCTION prevent_identity_physical_delete() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'physical identity deletion is disabled during data cutover';
        END;
        $$
        """
    )
    for table in IDENTITY_TABLES:
        op.execute(
            f"CREATE TRIGGER prevent_identity_physical_delete "
            f"BEFORE DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION prevent_identity_physical_delete()"
        )
        op.execute(
            f"CREATE TRIGGER prevent_identity_truncate "
            f"BEFORE TRUNCATE ON {table} FOR EACH STATEMENT "
            "EXECUTE FUNCTION prevent_identity_physical_delete()"
        )
    for name, table, _, _, _ in IDENTITY_REFERENCES:
        op.drop_constraint(name, table, type_="foreignkey")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    # PostgreSQL validates every recreated FK before we remove the delete guard.
    for name, table, target, columns, target_columns in IDENTITY_REFERENCES:
        op.create_foreign_key(name, table, target, list(columns), list(target_columns))
    for table in reversed(IDENTITY_TABLES):
        # A pre-release checkout may have applied this revision before the
        # truncate guard was added; its absence must not block rollback.
        op.execute(f"DROP TRIGGER IF EXISTS prevent_identity_truncate ON {table}")
        op.execute(f"DROP TRIGGER prevent_identity_physical_delete ON {table}")
    op.execute("DROP FUNCTION prevent_identity_physical_delete()")
