import logging
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.engine import make_engine
from app.features.ai.models import AIAnalysis
from app.features.ai.worker import process_ai_job
from app.features.audit.models import AuditRun
from app.features.audit.worker import process_audit_job
from app.features.audit_trail.events import append_business_event
from app.features.ingestion.models import ImportBatch, ImportRow, Job, Purchase, Supplier
from app.features.ingestion.parsing import bounded_rows, normalize, table_rows
from app.features.ingestion.routes import storage_path

logger = logging.getLogger(__name__)


def claim_job(db: Session) -> uuid.UUID | None:
    types = (
        ["import", "ai"]
        if settings.audit_dispatch_mode == "broker"
        else ["import", "audit", "ai"]
    )
    exhausted = db.scalar(
        select(Job)
        .where(
            Job.type.in_(types),
            Job.status == "running",
            Job.lease_until < datetime.now(UTC),
            Job.attempt_count >= 3,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if exhausted is not None:
        exhausted.status = "failed"
        exhausted.error_code = "lease_expired"
        exhausted.lease_until = None
        mark_target_failed(db, exhausted)
        db.commit()
    job = db.scalar(
        select(Job)
        .where(
            Job.type.in_(types),
            or_(
                Job.status == "queued",
                (Job.status == "running") & (Job.lease_until < datetime.now(UTC)),
            ),
            Job.attempt_count < 3,
        )
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.attempt_count += 1
    job.lease_until = datetime.now(UTC) + timedelta(hours=1)
    job.error_code = None
    db.commit()
    return job.id


def process_job(db: Session, job_id: uuid.UUID) -> None:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None or job.status != "running":
        return
    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == uuid.UUID(job.payload_json["batch_id"]),
            ImportBatch.organization_id == job.organization_id,
        )
    )
    if batch is None or not batch.mapping:
        raise ValueError("missing_batch_or_mapping")
    organization_id = job.organization_id
    batch_id = batch.id
    batch.status = "running"
    mapping = batch.mapping["columns"]
    rows = bounded_rows(
        table_rows(
            storage_path(batch),
            batch.file_format,
            batch.mapping.get("encoding"),
            batch.mapping.get("delimiter"),
        )
    )
    try:
        _, headers = next(rows)
    except StopIteration as exc:
        raise ValueError("empty_file") from exc
    if len(headers) != len(set(headers)) or not set(mapping.values()) <= set(headers):
        raise ValueError("headers_changed")
    row_count = 0
    error_count = 0
    seen_purchase_ids: set[str] = set()
    supplier_ids: dict[str, uuid.UUID] = {}
    for number, values in rows:
        raw = dict(zip(headers, values, strict=False))
        normalized, errors = normalize(raw, mapping)
        if len(values) != len(headers):
            errors.append(
                {"field": "_row", "code": "column_count", "message": "Número de colunas inválido"}
            )
        external_id = normalized.get("purchase_id", "")
        if external_id and external_id in seen_purchase_ids:
            errors.append(
                {
                    "field": "purchase_id",
                    "code": "duplicate_id",
                    "message": "ID de compra repetido nesta importação",
                }
            )
        elif external_id:
            seen_purchase_ids.add(external_id)
        row = ImportRow(
            id=uuid.uuid4(),
            organization_id=batch.organization_id,
            batch_id=batch.id,
            row_number=number,
            raw_json=raw,
            normalized_json=normalized if not errors else None,
            errors=errors,
        )
        db.add(row)
        row_count += 1
        if errors:
            error_count += 1
        else:
            supplier_external = normalized["supplier_id"]
            supplier_id = supplier_ids.get(supplier_external)
            if supplier_id is None:
                db.execute(
                    insert(Supplier)
                    .values(
                        id=uuid.uuid4(),
                        organization_id=batch.organization_id,
                        external_id=supplier_external,
                        name=normalized.get("supplier_name") or None,
                    )
                    .on_conflict_do_nothing(index_elements=["organization_id", "external_id"])
                )
                supplier_id = db.scalar(
                    select(Supplier.id).where(
                        Supplier.organization_id == batch.organization_id,
                        Supplier.external_id == supplier_external,
                    )
                )
                if supplier_id is None:
                    raise ValueError("supplier_missing")
                supplier_ids[supplier_external] = supplier_id
            db.add(
                Purchase(
                    organization_id=batch.organization_id,
                    batch_id=batch.id,
                    import_row_id=row.id,
                    supplier_id=supplier_id,
                    external_purchase_id=normalized["purchase_id"],
                    product_id=normalized["product_id"],
                    product_name=normalized.get("product_name") or None,
                    purchase_date=date.fromisoformat(normalized["purchase_date"]),
                    quantity=Decimal(normalized["quantity"]),
                    unit_of_measure=normalized.get("unit_of_measure") or None,
                    unit_price=Decimal(normalized["unit_price"]),
                    declared_total=Decimal(normalized["total_amount"]),
                    currency=normalized["currency"],
                    expected_delivery_date=date.fromisoformat(normalized["expected_delivery_date"])
                    if normalized.get("expected_delivery_date")
                    else None,
                    actual_delivery_date=date.fromisoformat(normalized["actual_delivery_date"])
                    if normalized.get("actual_delivery_date")
                    else None,
                )
            )
        if row_count % 500 == 0:
            db.flush()
            db.expunge_all()
            job = db.scalar(
                select(Job).where(Job.id == job_id, Job.organization_id == organization_id)
            )
            batch = db.scalar(
                select(ImportBatch).where(
                    ImportBatch.id == batch_id, ImportBatch.organization_id == organization_id
                )
            )
            if job is None or batch is None:
                raise ValueError("job_or_batch_missing")
    batch.row_count = row_count
    batch.error_count = error_count
    batch.status = "succeeded"
    job.status = "succeeded"
    job.lease_until = None
    append_business_event(
        db,
        batch.organization_id,
        None,
        "import.completed",
        "import",
        batch.id,
        {"row_count": row_count, "error_count": error_count},
    )
    db.commit()


def mark_target_failed(db: Session, job: Job) -> None:
    if job.type == "import":
        batch = db.scalar(
            select(ImportBatch).where(
                ImportBatch.id == uuid.UUID(job.payload_json["batch_id"]),
                ImportBatch.organization_id == job.organization_id,
            )
        )
        if batch is not None:
            batch.status = "failed"
    elif job.type == "audit":
        run = db.scalar(
            select(AuditRun).where(
                AuditRun.id == uuid.UUID(job.payload_json["audit_id"]),
                AuditRun.organization_id == job.organization_id,
            )
        )
        if run is not None:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.limitation = f"Falha no processamento ({job.error_code or 'unknown'})."
    elif job.type == "ai":
        analysis = db.scalar(
            select(AIAnalysis).where(
                AIAnalysis.id == uuid.UUID(job.payload_json["analysis_id"]),
                AIAnalysis.organization_id == job.organization_id,
            )
        )
        if analysis is not None:
            analysis.status = "failed"
            analysis.limitation = "Falha no processamento da IA. A auditoria permanece disponível."


def run_once() -> bool:
    with Session(make_engine()) as db:
        job_id = claim_job(db)
        if job_id is None:
            return False
        try:
            job = db.get(Job, job_id)
            if job is None:
                return True
            if job.type == "audit":
                process_audit_job(db, job_id)
            elif job.type == "ai":
                process_ai_job(db, job_id)
            else:
                process_job(db, job_id)
        except Exception as exc:
            logger.exception("Job failed: %s", type(exc).__name__)
            db.rollback()
            job = db.get(Job, job_id)
            if job is not None:
                permanent = isinstance(exc, (ApiError, ValueError))
                job.status = "failed" if permanent or job.attempt_count >= 3 else "queued"
                job.error_code = exc.code if isinstance(exc, ApiError) else type(exc).__name__[:80]
                job.lease_until = None
                if job.status == "failed":
                    mark_target_failed(db, job)
                elif job.type == "import":
                    batch = db.scalar(
                        select(ImportBatch).where(
                            ImportBatch.id == uuid.UUID(job.payload_json["batch_id"]),
                            ImportBatch.organization_id == job.organization_id,
                        )
                    )
                    if batch is not None:
                        batch.status = "queued"
                elif job.type == "audit":
                    run = db.scalar(
                        select(AuditRun).where(
                            AuditRun.id == uuid.UUID(job.payload_json["audit_id"]),
                            AuditRun.organization_id == job.organization_id,
                        )
                    )
                    if run is not None:
                        run.status = "queued"
                elif job.type == "ai":
                    analysis = db.scalar(
                        select(AIAnalysis).where(
                            AIAnalysis.id == uuid.UUID(job.payload_json["analysis_id"]),
                            AIAnalysis.organization_id == job.organization_id,
                        )
                    )
                    if analysis is not None:
                        analysis.status = "queued"
                db.commit()
    return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
