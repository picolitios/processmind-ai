"""Add per-organization agent capabilities and managed knowledge sources.

Revision ID: e8a91f76c203
Revises: d7b4e6a192c0
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e8a91f76c203"
down_revision = "d7b4e6a192c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_configurations",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("agent_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("purchasing_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by_user_id", sa.Uuid()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="business",
    )
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_source_org_id"),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 160", name="ck_knowledge_title"),
        sa.CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="ck_knowledge_content"),
        sa.CheckConstraint("revision > 0", name="ck_knowledge_revision"),
        schema="business",
    )
    op.create_index(
        "ix_knowledge_source_org_enabled",
        "knowledge_sources",
        ["organization_id", "enabled", "created_at", "id"],
        schema="business",
    )
    op.execute("""
        CREATE INDEX ix_knowledge_source_search ON business.knowledge_sources
        USING gin (to_tsvector('portuguese'::regconfig,
            coalesce(title, '') || ' ' || coalesce(content, '')))
    """)
    op.add_column(
        "copilot_turns",
        sa.Column("knowledge_ids", JSONB(), nullable=False, server_default="[]"),
        schema="business",
    )
    op.add_column(
        "copilot_turns",
        sa.Column("knowledge_revisions", JSONB(), nullable=False, server_default="{}"),
        schema="business",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON business.agent_configurations, "
        "business.knowledge_sources TO processmind_business"
    )


def downgrade() -> None:
    # Reverting with active documents or saved document citations would lose business evidence.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM business.knowledge_sources)
             OR EXISTS (SELECT 1 FROM business.agent_configurations)
             OR EXISTS (SELECT 1 FROM business.copilot_turns WHERE knowledge_ids <> '[]'::jsonb)
          THEN
            RAISE EXCEPTION 'enterprise agent data must be preserved before downgrade';
          END IF;
        END $$
    """)
    op.drop_column("copilot_turns", "knowledge_ids", schema="business")
    op.drop_column("copilot_turns", "knowledge_revisions", schema="business")
    op.drop_index("ix_knowledge_source_search", table_name="knowledge_sources", schema="business")
    op.drop_index(
        "ix_knowledge_source_org_enabled", table_name="knowledge_sources", schema="business"
    )
    op.drop_table("knowledge_sources", schema="business")
    op.drop_table("agent_configurations", schema="business")
