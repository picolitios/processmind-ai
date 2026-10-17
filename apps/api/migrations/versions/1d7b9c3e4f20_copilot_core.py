"""Add business-owned copilot policy, conversations and turns.

Revision ID: 1d7b9c3e4f20
Revises: 82f6c4d1a9e0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "1d7b9c3e4f20"
down_revision: str | None = "82f6c4d1a9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_policies",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("temporary_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("memory_turn_limit", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("memory_turn_limit BETWEEN 0 AND 20"),
        schema="business",
    )
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid()),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decided_by", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["business.audit_findings.organization_id", "business.audit_findings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["business.audit_runs.organization_id", "business.audit_runs.id"],
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_copilot_conversation_org_id"),
        sa.CheckConstraint("(finding_id IS NULL) <> (run_id IS NULL)", name="ck_copilot_target"),
        sa.CheckConstraint("mode IN ('normal','temporary')", name="ck_copilot_mode"),
        sa.CheckConstraint("status IN ('active','pending','rejected')", name="ck_copilot_status"),
        sa.CheckConstraint("mode = 'temporary' OR expires_at IS NULL", name="ck_copilot_expiry"),
        schema="business",
    )
    op.create_index(
        "ix_copilot_conversation_author", "copilot_conversations",
        ["organization_id", "author_id", "created_at", "id"], schema="business",
    )
    op.create_index(
        "ix_copilot_conversation_pending", "copilot_conversations",
        ["organization_id", "status", "created_at", "id"], schema="business",
    )
    op.create_index(
        "ix_copilot_conversation_expiry", "copilot_conversations",
        ["expires_at"], schema="business",
    )
    op.create_table(
        "copilot_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("answer", sa.Text()),
        sa.Column("evidence_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("context_hash", sa.String(64)),
        sa.Column("model", sa.String(120)),
        sa.Column("limitation", sa.String(500)),
        sa.Column("job_id", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["business.copilot_conversations.organization_id", "business.copilot_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "job_id"], ["business.jobs.organization_id", "business.jobs.id"]
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_copilot_turn_org_id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_copilot_turn_org_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')", name="ck_copilot_turn_status"
        ),
        schema="business",
    )
    op.create_index(
        "ix_copilot_turn_conversation", "copilot_turns",
        ["organization_id", "conversation_id", "created_at", "id"], schema="business",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA business "
        "TO processmind_business"
    )


def downgrade() -> None:
    # An operator must export or intentionally remove chats before this rollback.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM business.copilot_conversations)
             OR EXISTS (SELECT 1 FROM business.copilot_turns)
             OR EXISTS (SELECT 1 FROM business.copilot_policies)
          THEN RAISE EXCEPTION 'copilot data must be preserved before downgrade';
          END IF;
        END $$
    """)
    op.drop_table("copilot_turns", schema="business")
    op.drop_table("copilot_conversations", schema="business")
    op.drop_table("copilot_policies", schema="business")
