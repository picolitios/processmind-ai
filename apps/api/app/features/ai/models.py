import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    requester_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str | None] = mapped_column(String(120))
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    limitation: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "run_id"], ["audit_runs.organization_id", "audit_runs.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["audit_findings.organization_id", "audit_findings.id"],
        ),
        ForeignKeyConstraint(["organization_id", "job_id"], ["jobs.organization_id", "jobs.id"]),
        UniqueConstraint("organization_id", "id", name="uq_ai_analysis_org_id"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_ai_analysis_org_key"),
        Index("ix_ai_analysis_org_status_created", "organization_id", "status", "created_at"),
        CheckConstraint("(run_id IS NULL) <> (finding_id IS NULL)", name="ck_ai_one_target"),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_ai_status"),
    )
