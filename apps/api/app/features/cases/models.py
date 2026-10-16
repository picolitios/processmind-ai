import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditCase(Base):
    __tablename__ = "audit_cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="open")
    closure_reason: Mapped[str | None] = mapped_column(String(1000))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["audit_findings.organization_id", "audit_findings.id"],
        ),
        UniqueConstraint("organization_id", "id", name="uq_case_org_id"),
        UniqueConstraint("organization_id", "finding_id", name="uq_case_org_finding"),
        Index("ix_case_org_status_opened", "organization_id", "status", "opened_at", "id"),
        Index("ix_case_org_assignee", "organization_id", "assignee_membership_id"),
        CheckConstraint(
            "status IN ('open','in_review','resolved','dismissed')", name="ck_case_status"
        ),
    )


class CaseComment(Base):
    __tablename__ = "case_comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    author_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "case_id"], ["audit_cases.organization_id", "audit_cases.id"]
        ),
        Index("ix_case_comment_org_case_time", "organization_id", "case_id", "created_at", "id"),
        CheckConstraint("length(trim(body)) BETWEEN 1 AND 5000", name="ck_case_comment_length"),
    )
