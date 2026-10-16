import hashlib
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, text

from app.core.config import settings
from app.core.errors import ApiError
from app.features.audit_trail.events import log_business_event as log_event
from app.features.identity.client import BusinessAuth as Auth
from app.features.identity.client import BusinessCsrfAuth as CsrfAuth
from app.features.identity.client import require_business_membership as require_membership
from app.features.identity.security import DB
from app.features.ingestion.models import ImportBatch, ImportRow, Job, Purchase, Supplier
from app.features.ingestion.parsing import preview, validate_mapping

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["imports"])
WRITERS = {"owner", "admin", "analyst"}


class MappingInput(BaseModel):
    columns: dict[str, str]
    delimiter: str | None = None
    encoding: str | None = None


def storage_path(batch: ImportBatch) -> Path:
    return Path(settings.upload_dir) / batch.private_storage_key


def import_view(db: DB, batch: ImportBatch) -> dict[str, Any]:
    job = db.scalar(
        select(Job).where(
            Job.organization_id == batch.organization_id,
            Job.type == "import",
            Job.idempotency_key == str(batch.id),
        )
    )
    return {
        "id": batch.id,
        "status": batch.status,
        "filename": batch.original_name,
        "row_count": batch.row_count,
        "error_count": batch.error_count,
        "job": {"id": job.id, "status": job.status, "error_code": job.error_code} if job else None,
    }


def get_batch(db: DB, organization_id: uuid.UUID, import_id: uuid.UUID) -> ImportBatch:
    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.organization_id == organization_id, ImportBatch.id == import_id
        )
    )
    if batch is None:
        raise ApiError(404, "not_found", "Importação não encontrada")
    return batch


def lock_import_deduplication(db: DB, organization_id: uuid.UUID) -> None:
    # A transaction-scoped, domain-prefixed key serializes same-tenant hash and idempotency checks.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"processmind:import:{organization_id}"},
    )


@router.post("/imports", status_code=201)
async def upload_import(
    organization_id: uuid.UUID,
    request: Request,
    db: DB,
    auth: CsrfAuth,
    file: Annotated[UploadFile, File()],
    reimport_reason: str | None = Form(None),
    idempotency_key: str | None = Header(None),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    filename = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    file_format = Path(filename).suffix.lower().lstrip(".")
    if file_format not in {"csv", "xlsx"}:
        raise ApiError(422, "invalid_file", "Envie CSV ou XLSX")
    if idempotency_key and len(idempotency_key) > 128:
        raise ApiError(422, "invalid_key", "Idempotency-Key inválida")
    if reimport_reason is not None and not (1 <= len(reimport_reason.strip()) <= 500):
        raise ApiError(422, "invalid_reason", "Motivo de reimportação inválido")
    storage = Path(settings.upload_dir)
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = uuid.uuid4().hex
    path = storage / key
    hasher = hashlib.sha256()
    total = 0
    try:
        with path.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise ApiError(413, "file_too_large", "Arquivo excede limite de upload")
                output.write(chunk)
                hasher.update(chunk)
        if total == 0:
            raise ApiError(422, "empty_file", "Arquivo vazio")
        preview(path, file_format)
        sha = hasher.hexdigest()
        lock_import_deduplication(db, organization_id)
        if idempotency_key:
            prior = db.scalar(
                select(ImportBatch).where(
                    ImportBatch.organization_id == organization_id,
                    ImportBatch.idempotency_key == idempotency_key,
                )
            )
            if prior:
                if prior.sha256 != sha:
                    raise ApiError(409, "idempotency_conflict", "Chave já usada para outro arquivo")
                path.unlink(missing_ok=True)
                return import_view(db, prior)
        duplicate = db.scalar(
            select(ImportBatch.id)
            .where(ImportBatch.organization_id == organization_id, ImportBatch.sha256 == sha)
            .limit(1)
        )
        if duplicate and not reimport_reason:
            raise ApiError(409, "duplicate_file", "Arquivo já importado nesta organização")
        batch = ImportBatch(
            organization_id=organization_id,
            uploader_id=auth.user.id,
            sha256=sha,
            original_name=filename,
            private_storage_key=key,
            file_format=file_format,
            idempotency_key=idempotency_key,
            reimport_reason=reimport_reason.strip() if reimport_reason else None,
        )
        db.add(batch)
        db.flush()
        log_event(db, request, "import.uploaded", auth.user.id, "import", batch.id, organization_id)
        db.commit()
        return import_view(db, batch)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/imports")
def list_imports(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(50, ge=1, le=100),
    cursor: int = Query(0, ge=0),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    items = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.organization_id == organization_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        .offset(cursor)
        .limit(limit + 1)
    ).all()
    return {
        "items": [import_view(db, item) for item in items[:limit]],
        "next_cursor": str(cursor + limit) if len(items) > limit else None,
    }


@router.get("/imports/{import_id}")
def get_import(
    organization_id: uuid.UUID, import_id: uuid.UUID, db: DB, auth: Auth
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    return import_view(db, get_batch(db, organization_id, import_id))


@router.get("/imports/{import_id}/preview")
def get_preview(
    organization_id: uuid.UUID, import_id: uuid.UUID, db: DB, auth: Auth
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    batch = get_batch(db, organization_id, import_id)
    return preview(storage_path(batch), batch.file_format)


@router.post("/imports/{import_id}/confirm", status_code=202)
def confirm_import(
    organization_id: uuid.UUID,
    import_id: uuid.UUID,
    data: MappingInput,
    request: Request,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    batch = db.scalar(
        select(ImportBatch)
        .where(ImportBatch.organization_id == organization_id, ImportBatch.id == import_id)
        .with_for_update()
    )
    if batch is None:
        raise ApiError(404, "not_found", "Importação não encontrada")
    if batch.status != "preview":
        raise ApiError(409, "invalid_state", "Importação já confirmada")
    if batch.file_format == "xlsx" and (data.delimiter or data.encoding):
        raise ApiError(422, "invalid_mapping", "Opções de CSV não se aplicam ao XLSX")
    sample = preview(storage_path(batch), batch.file_format)
    validate_mapping(data.columns, sample["headers"])
    if data.delimiter and data.delimiter not in {",", ";", "\t"}:
        raise ApiError(422, "invalid_delimiter", "Delimitador inválido")
    if data.encoding and data.encoding not in {"utf-8", "utf-8-sig"}:
        raise ApiError(422, "invalid_encoding", "Codificação inválida")
    batch.mapping = data.model_dump(exclude_none=True)
    batch.status = "queued"
    job = Job(
        organization_id=organization_id,
        type="import",
        status="queued",
        payload_json={"batch_id": str(batch.id)},
        idempotency_key=str(batch.id),
    )
    db.add(job)
    db.flush()
    log_event(db, request, "import.queued", auth.user.id, "import", batch.id, organization_id)
    db.commit()
    return {"id": job.id, "status": job.status}


@router.get("/imports/{import_id}/rows")
def list_rows(
    organization_id: uuid.UUID,
    import_id: uuid.UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(50, ge=1, le=100),
    cursor: int = Query(0, ge=0),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    get_batch(db, organization_id, import_id)
    rows = db.scalars(
        select(ImportRow)
        .where(
            ImportRow.organization_id == organization_id,
            ImportRow.batch_id == import_id,
            ImportRow.row_number > cursor,
        )
        .order_by(ImportRow.row_number)
        .limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "row_number": row.row_number,
                "normalized": row.normalized_json,
                "errors": row.errors,
                "raw": row.raw_json,
            }
            for row in rows[:limit]
        ],
        "next_cursor": str(rows[limit - 1].row_number) if len(rows) > limit else None,
    }


@router.get("/purchases")
def list_purchases(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    import_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    cursor: int = Query(0, ge=0),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    statement = (
        select(Purchase, Supplier.external_id, Supplier.name)
        .join(
            Supplier,
            (Supplier.organization_id == Purchase.organization_id)
            & (Supplier.id == Purchase.supplier_id),
        )
        .where(Purchase.organization_id == organization_id)
    )
    if import_id:
        statement = statement.where(Purchase.batch_id == import_id)
    rows = db.execute(
        statement.order_by(Purchase.created_at, Purchase.id).offset(cursor).limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "id": purchase.id,
                "purchase_id": purchase.external_purchase_id,
                "supplier_id": supplier_external_id,
                "supplier_name": supplier_name,
                "product_id": purchase.product_id,
                "product_name": purchase.product_name,
                "purchase_date": purchase.purchase_date,
                "quantity": str(purchase.quantity),
                "unit_of_measure": purchase.unit_of_measure,
                "unit_price": str(purchase.unit_price),
                "total_amount": str(purchase.declared_total),
                "currency": purchase.currency,
                "expected_delivery_date": purchase.expected_delivery_date,
                "actual_delivery_date": purchase.actual_delivery_date,
            }
            for purchase, supplier_external_id, supplier_name in rows[:limit]
        ],
        "next_cursor": str(cursor + limit) if len(rows) > limit else None,
    }
