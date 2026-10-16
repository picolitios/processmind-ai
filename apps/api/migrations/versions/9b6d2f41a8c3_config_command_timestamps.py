"""Require timestamps on audit configuration commands.

Revision ID: 9b6d2f41a8c3
Revises: 7f4a91c0b2e6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b6d2f41a8c3"
down_revision: str | None = "7f4a91c0b2e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Older local checkouts may have applied the prior revision before nullability was finalized.
    missing = op.get_bind().scalar(sa.text(
        "SELECT count(*) FROM organization_config_commands "
        "WHERE created_at IS NULL OR updated_at IS NULL"
    ))
    if missing:
        raise RuntimeError("configuration command timestamps require investigation")
    for column in ("created_at", "updated_at"):
        op.alter_column(
            "organization_config_commands", column,
            existing_type=sa.DateTime(timezone=True), nullable=False,
        )


def downgrade() -> None:
    # Relaxing nullability is non-destructive; the command rows remain intact.
    for column in ("created_at", "updated_at"):
        op.alter_column(
            "organization_config_commands", column,
            existing_type=sa.DateTime(timezone=True), nullable=True,
        )
