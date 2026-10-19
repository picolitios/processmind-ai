"""Fence abandoned broker attempts with an audit job token.

Revision ID: 4ad58c96e321
Revises: 1d7b9c3e4f20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4ad58c96e321"
down_revision: str | None = "1d7b9c3e4f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("attempt_token", sa.Uuid(), nullable=True), schema="business")


def downgrade() -> None:
    op.drop_column("jobs", "attempt_token", schema="business")
