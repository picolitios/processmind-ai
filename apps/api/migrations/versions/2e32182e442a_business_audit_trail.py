"""Add business-owned audit trail and backfill existing business events.

Revision ID: 2e32182e442a
Revises: 930ec2b28a32
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "2e32182e442a"
down_revision: str | None = "930ec2b28a32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("subject_type", sa.String(40), nullable=False),
        sa.Column("subject_id", sa.Uuid()),
        sa.Column("metadata_json", JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_business_event_org_subject_time",
        "business_audit_events",
        ["organization_id", "subject_type", "subject_id", "occurred_at", "id"],
    )
    # Copy only the five business action families; identity history stays in place.
    op.execute(
        sa.text(
            """
            INSERT INTO business_audit_events
                (id, organization_id, actor_user_id, action, subject_type,
                 subject_id, metadata_json, correlation_id, occurred_at)
            SELECT id, organization_id, actor_user_id, action, subject_type,
                   subject_id, metadata_json, correlation_id, occurred_at
            FROM audit_events
            WHERE organization_id IS NOT NULL
              AND split_part(action, '.', 1)
                  IN ('import', 'audit', 'ai', 'finding', 'case')
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_business_event_org_subject_time", table_name="business_audit_events")
    op.drop_table("business_audit_events")
