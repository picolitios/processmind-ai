"""Allow organization-wide consultative chats and index finding text.

Revision ID: a19c4e72b630
Revises: 4ad58c96e321
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a19c4e72b630"
down_revision: str | None = "4ad58c96e321"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Permit a null target pair to represent the owning organization."""
    op.drop_constraint("ck_copilot_target", "copilot_conversations", schema="business")
    op.create_check_constraint(
        "ck_copilot_target", "copilot_conversations",
        "finding_id IS NULL OR run_id IS NULL", schema="business",
    )
    op.execute("""
        CREATE INDEX ix_audit_finding_org_search
        ON business.audit_findings USING gin (
            to_tsvector('portuguese'::regconfig,
                coalesce(rule_code, '') || ' ' || coalesce(explanation, ''))
        )
    """)


def downgrade() -> None:
    """Refuse a rollback that would silently discard organization chats."""
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM business.copilot_conversations
            WHERE finding_id IS NULL AND run_id IS NULL
          ) THEN
            RAISE EXCEPTION 'organization chats must be preserved before downgrade';
          END IF;
        END $$
    """)
    op.drop_index("ix_audit_finding_org_search", table_name="audit_findings", schema="business")
    op.drop_constraint("ck_copilot_target", "copilot_conversations", schema="business")
    op.create_check_constraint(
        "ck_copilot_target", "copilot_conversations",
        "(finding_id IS NULL) <> (run_id IS NULL)", schema="business",
    )
