import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CopilotPolicy(Base):
    """Business-owned organization policy; an absent row means normal mode."""

    __tablename__ = "copilot_policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    temporary_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    memory_turn_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("memory_turn_limit BETWEEN 0 AND 20"),
        CheckConstraint("char_length(instructions) <= 2000", name="ck_copilot_instructions_length"),
    )


class CopilotConversation(Base):
    """Normal chats persist; temporary chats are short-lived job state."""

    __tablename__ = "copilot_conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["audit_findings.organization_id", "audit_findings.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "run_id"], ["audit_runs.organization_id", "audit_runs.id"]
        ),
        UniqueConstraint("organization_id", "id", name="uq_copilot_conversation_org_id"),
        Index("ix_copilot_conversation_author", "organization_id", "author_id", "created_at", "id"),
        Index("ix_copilot_conversation_pending", "organization_id", "status", "created_at", "id"),
        Index("ix_copilot_conversation_expiry", "expires_at"),
        CheckConstraint("finding_id IS NULL OR run_id IS NULL", name="ck_copilot_target"),
        CheckConstraint("mode IN ('normal','temporary')", name="ck_copilot_mode"),
        CheckConstraint("status IN ('active','pending','rejected')", name="ck_copilot_status"),
        CheckConstraint("mode = 'temporary' OR expires_at IS NULL", name="ck_copilot_expiry"),
    )


class CopilotTurn(Base):
    """A question and its validated answer, scoped to one conversation."""

    __tablename__ = "copilot_turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    answer: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    context_hash: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(120))
    limitation: Mapped[str | None] = mapped_column(String(500))
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["copilot_conversations.organization_id", "copilot_conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["organization_id", "job_id"], ["jobs.organization_id", "jobs.id"]),
        UniqueConstraint("organization_id", "id", name="uq_copilot_turn_org_id"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_copilot_turn_org_key"),
        Index(
            "ix_copilot_turn_conversation", "organization_id", "conversation_id", "created_at", "id"
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')", name="ck_copilot_turn_status"
        ),
    )
