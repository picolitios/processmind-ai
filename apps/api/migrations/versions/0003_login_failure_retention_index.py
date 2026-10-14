"""Index login failure age for bounded retention.

Revision ID: 0003_login_failure_time
Revises: 1c1e5d1ee128
"""

from alembic import op

revision = "0003_login_failure_time"
down_revision = "1c1e5d1ee128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_login_failure_time", "login_failures", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_login_failure_time", table_name="login_failures")
