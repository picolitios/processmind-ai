"""Add audit-owned configuration and backfill organization settings.

Revision ID: 930ec2b28a32
Revises: 52ca5ae80101
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "930ec2b28a32"
down_revision: str | None = "52ca5ae80101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_configurations",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("amount_limits", JSONB(), nullable=True),
        sa.Column("delay_window_days", sa.Integer(), nullable=True),
    )
    # Preserve explicit JSON nulls while supplying the same defaults as audit creation.
    op.execute(
        sa.text(
            """
            INSERT INTO audit_configurations
                (organization_id, settings_version, amount_limits, delay_window_days)
            SELECT id, settings_version,
                   CASE WHEN settings ? 'amount_limits'
                        THEN settings->'amount_limits' ELSE '{}'::jsonb END,
                   CASE WHEN settings ? 'delay_window_days'
                        THEN (settings->>'delay_window_days')::integer ELSE 90 END
            FROM organizations
            """
        )
    )


def downgrade() -> None:
    op.drop_table("audit_configurations")
