"""Add optional user names and pending organization invitations.

Revision ID: c4d2e8a971b0
Revises: a19c4e72b630
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d2e8a971b0"
down_revision = "a19c4e72b630"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(120)), schema="identity")
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True)), schema="identity"
    )
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id", sa.Uuid(),
            sa.ForeignKey("identity.organizations.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_by_user_id", sa.Uuid(),
            sa.ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('admin','analyst','viewer')", name="ck_invite_role"),
        schema="identity",
    )
    op.create_index(
        "ix_invite_org_created", "organization_invites",
        ["organization_id", "created_at", "id"], schema="identity",
    )
    op.create_index(
        "ix_invite_email_active", "organization_invites",
        ["email", "expires_at"], schema="identity",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON identity.organization_invites "
        "TO processmind_identity"
    )


def downgrade() -> None:
    op.drop_index("ix_invite_email_active", table_name="organization_invites", schema="identity")
    op.drop_index("ix_invite_org_created", table_name="organization_invites", schema="identity")
    op.drop_table("organization_invites", schema="identity")
    op.drop_column("users", "display_name", schema="identity")
    op.drop_column("users", "email_verified_at", schema="identity")
