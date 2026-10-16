import uuid
from datetime import datetime
from typing import Any

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


class AuditConfiguration(Base):
    """Versioned audit settings owned by the audit domain."""

    __tablename__ = "audit_configurations"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    last_command_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    amount_limits: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    delay_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditRun(Base):
    __tablename__ = "audit_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    requester_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    rule_set_version: Mapped[str] = mapped_column(String(20))
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    import_ids: Mapped[list[str]] = mapped_column(JSONB)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    limitation: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "job_id"], ["jobs.organization_id", "jobs.id"]),
        UniqueConstraint("organization_id", "id", name="uq_audit_run_org_id"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_audit_run_org_key"),
        Index("ix_audit_run_org_created", "organization_id", "created_at", "id"),
        CheckConstraint("status IN ('queued','running','succeeded','failed')"),
    )


class AuditRule(Base):
    __tablename__ = "audit_rules"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled_by_default: Mapped[bool] = mapped_column(Boolean, default=True)
    parameter_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    rule_code: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    review_state: Mapped[str] = mapped_column(String(20), default="unreviewed")
    explanation: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "run_id"], ["audit_runs.organization_id", "audit_runs.id"]
        ),
        ForeignKeyConstraint(
            ["rule_code", "rule_version"], ["audit_rules.code", "audit_rules.version"]
        ),
        UniqueConstraint("organization_id", "id", name="uq_audit_finding_org_id"),
        UniqueConstraint(
            "organization_id", "run_id", "fingerprint", name="uq_audit_finding_fingerprint"
        ),
        Index("ix_audit_finding_org_run", "organization_id", "run_id"),
        Index("ix_audit_finding_org_state", "organization_id", "review_state", "severity"),
        CheckConstraint("severity IN ('low','medium','high','critical')"),
        CheckConstraint("review_state IN ('unreviewed','in_review','resolved','dismissed')"),
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    import_row_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["audit_findings.organization_id", "audit_findings.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "purchase_id"], ["purchases.organization_id", "purchases.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "import_row_id"], ["import_rows.organization_id", "import_rows.id"]
        ),
        CheckConstraint("purchase_id IS NOT NULL OR import_row_id IS NOT NULL"),
        Index("ix_evidence_org_finding", "organization_id", "finding_id"),
    )
