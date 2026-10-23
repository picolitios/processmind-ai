"""Add organization instructions to the business-owned AI policy.

Revision ID: d7b4e6a192c0
Revises: c4d2e8a971b0
"""

import sqlalchemy as sa
from alembic import op

revision = "d7b4e6a192c0"
down_revision = "c4d2e8a971b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "copilot_policies",
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        schema="business",
    )
    op.create_check_constraint(
        "ck_copilot_instructions_length", "copilot_policies",
        "char_length(instructions) <= 2000", schema="business",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_copilot_instructions_length", "copilot_policies", schema="business",
    )
    op.drop_column("copilot_policies", "instructions", schema="business")
