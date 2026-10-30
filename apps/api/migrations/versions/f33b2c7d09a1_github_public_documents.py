"""Add verifiable public GitHub document provenance to knowledge sources.

Revision ID: f33b2c7d09a1
Revises: e8a91f76c203
"""

import sqlalchemy as sa
from alembic import op

revision = "f33b2c7d09a1"
down_revision = "e8a91f76c203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("source_type", sa.String(32), nullable=False, server_default="managed_knowledge"),
        schema="business",
    )
    for name, column in (
        ("github_owner", sa.String(39)),
        ("github_repo", sa.String(100)),
        ("github_path", sa.String(240)),
        ("github_blob_sha", sa.String(40)),
        ("github_checked_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("knowledge_sources", sa.Column(name, column), schema="business")
    op.create_check_constraint(
        "ck_knowledge_origin",
        "knowledge_sources",
        "(source_type = 'managed_knowledge' AND github_owner IS NULL "
        "AND github_repo IS NULL AND github_path IS NULL AND github_blob_sha IS NULL "
        "AND github_checked_at IS NULL) "
        "OR (source_type = 'github_public' AND github_owner IS NOT NULL "
        "AND github_repo IS NOT NULL AND github_path IS NOT NULL "
        "AND github_blob_sha IS NOT NULL AND github_checked_at IS NOT NULL)",
        schema="business",
    )
    op.create_index(
        "uq_knowledge_github_path", "knowledge_sources",
        ["organization_id", "github_owner", "github_repo", "github_path"],
        unique=True, schema="business",
    )


def downgrade() -> None:
    # Never strip the origin and SHA from a source that might have been cited.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM business.knowledge_sources
                     WHERE source_type = 'github_public') THEN
            RAISE EXCEPTION 'remove GitHub sources before downgrade';
          END IF;
        END $$
    """)
    op.drop_index("uq_knowledge_github_path", table_name="knowledge_sources", schema="business")
    op.drop_constraint("ck_knowledge_origin", "knowledge_sources", type_="check", schema="business")
    for name in (
        "github_checked_at", "github_blob_sha", "github_path", "github_repo", "github_owner",
        "source_type",
    ):
        op.drop_column("knowledge_sources", name, schema="business")
