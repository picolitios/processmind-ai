import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    uploader_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    sha256: Mapped[str] = mapped_column(String(64))
    original_name: Mapped[str] = mapped_column(String(255))
    private_storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    file_format: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(20), default="preview")
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    reimport_reason: Mapped[str | None] = mapped_column(String(500))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_import_org_id"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_import_org_idempotency"),
        Index("ix_import_org_hash", "organization_id", "sha256"),
        Index("ix_import_org_created", "organization_id", "created_at", "id"),
        CheckConstraint("status IN ('preview','queued','running','succeeded','failed')"),
    )


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    row_number: Mapped[int] = mapped_column(Integer)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    normalized_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    errors: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "batch_id"],
            ["import_batches.organization_id", "import_batches.id"],
        ),
        UniqueConstraint("organization_id", "id", name="uq_import_row_org_id"),
        UniqueConstraint("batch_id", "row_number", name="uq_import_row_batch_number"),
        Index("ix_import_row_org_batch_number", "organization_id", "batch_id", "row_number"),
    )


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    external_id: Mapped[str] = mapped_column(String(160))
    name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_supplier_org_id"),
        UniqueConstraint("organization_id", "external_id", name="uq_supplier_org_external"),
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    import_row_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    external_purchase_id: Mapped[str] = mapped_column(String(160))
    product_id: Mapped[str] = mapped_column(String(160))
    product_name: Mapped[str | None] = mapped_column(String(255))
    purchase_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_of_measure: Mapped[str | None] = mapped_column(String(40))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    declared_total: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    currency: Mapped[str] = mapped_column(String(3))
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "batch_id"], ["import_batches.organization_id", "import_batches.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "import_row_id"], ["import_rows.organization_id", "import_rows.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"], ["suppliers.organization_id", "suppliers.id"]
        ),
        UniqueConstraint("organization_id", "id", name="uq_purchase_org_id"),
        UniqueConstraint("import_row_id", name="uq_purchase_import_row"),
        Index("ix_purchase_org_batch", "organization_id", "batch_id"),
        Index("ix_purchase_org_product_date", "organization_id", "product_id", "purchase_date"),
        Index("ix_purchase_org_supplier_date", "organization_id", "supplier_id", "purchase_date"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    attempt_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_job_org_id"),
        UniqueConstraint("organization_id", "type", "idempotency_key", name="uq_job_org_type_key"),
        Index("ix_job_status_lease", "status", "lease_until"),
        CheckConstraint("status IN ('queued','running','succeeded','failed')"),
    )
