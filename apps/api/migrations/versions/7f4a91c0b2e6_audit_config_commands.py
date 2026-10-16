"""Add identity-owned audit configuration command ledger.

Revision ID: 7f4a91c0b2e6
Revises: 2e32182e442a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "7f4a91c0b2e6"
down_revision: str | None = "2e32182e442a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_configurations", sa.Column("last_command_id", sa.Uuid()))
    op.create_table(
        "organization_config_commands",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount_limits", JSONB()),
        sa.Column("delay_window_days", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('provision','update')", name="ck_org_config_command_kind"),
        sa.CheckConstraint(
            "status IN ('pending','applied','blocked')", name="ck_org_config_command_status"
        ),
        sa.UniqueConstraint(
            "organization_id", "settings_version", name="uq_org_config_command_version"
        ),
    )
    op.create_index(
        "ix_org_config_command_status_created",
        "organization_config_commands",
        ["status", "created_at", "id"],
    )


def downgrade() -> None:
    # Refuse to discard command history or applied IDs during an older-code rollback.
    bind = op.get_bind()
    commands = bind.scalar(sa.text("SELECT count(*) FROM organization_config_commands"))
    applied_ids = bind.scalar(sa.text(
        "SELECT count(*) FROM audit_configurations WHERE last_command_id IS NOT NULL"
    ))
    if commands or applied_ids:
        raise RuntimeError("audit configuration commands must be retained for rollback")
    op.drop_index("ix_org_config_command_status_created", table_name="organization_config_commands")
    op.drop_table("organization_config_commands")
    op.drop_column("audit_configurations", "last_command_id")
