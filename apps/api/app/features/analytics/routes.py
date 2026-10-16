import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.errors import ApiError
from app.features.audit.models import AuditFinding, AuditRun
from app.features.cases.models import AuditCase
from app.features.identity.client import BusinessAuth as Auth
from app.features.identity.client import require_business_membership as require_membership
from app.features.identity.security import DB
from app.features.ingestion.models import ImportBatch, Purchase, Supplier

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/analytics", tags=["analytics"])


def bounds(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    if start and end and end < start:
        raise ApiError(422, "invalid_period", "Data final anterior à inicial")
    return (
        datetime.combine(start, time.min, UTC) if start else None,
        datetime.combine(end + timedelta(days=1), time.min, UTC)
        if end and end != date.max
        else None,
    )


def dated(statement: Any, column: Any, start: datetime | None, end: datetime | None) -> Any:
    if start:
        statement = statement.where(column >= start)
    if end:
        statement = statement.where(column < end)
    return statement


@router.get("/overview")
def overview(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    start, end = bounds(date_from, date_to)
    imports = (
        db.scalar(
            dated(
                select(func.count())
                .select_from(ImportBatch)
                .where(ImportBatch.organization_id == organization_id),
                ImportBatch.created_at,
                start,
                end,
            )
        )
        or 0
    )
    runs = db.scalars(
        dated(
            select(AuditRun.import_ids).where(
                AuditRun.organization_id == organization_id,
                AuditRun.status == "succeeded",
            ),
            AuditRun.created_at,
            start,
            end,
        )
    ).all()
    audited_batches = {uuid.UUID(item) for import_ids in runs for item in import_ids}
    purchase_filter = [Purchase.organization_id == organization_id]
    if audited_batches:
        purchase_filter.append(Purchase.batch_id.in_(audited_batches))
    else:
        purchase_filter.append(Purchase.id.is_(None))
    purchase_start = date_from
    purchase_end = date_to
    if purchase_start:
        purchase_filter.append(Purchase.purchase_date >= purchase_start)
    if purchase_end:
        purchase_filter.append(Purchase.purchase_date <= purchase_end)
    analyzed_records = (
        db.scalar(select(func.count()).select_from(Purchase).where(*purchase_filter)) or 0
    )
    severity_rows = db.execute(
        dated(
            select(AuditFinding.severity, func.count())
            .where(
                AuditFinding.organization_id == organization_id,
            )
            .group_by(AuditFinding.severity),
            AuditFinding.detected_at,
            start,
            end,
        )
    ).all()
    findings_by_severity = {severity: count for severity, count in severity_rows}
    case_query = dated(
        select(AuditCase.status, func.count())
        .where(
            AuditCase.organization_id == organization_id,
        )
        .group_by(AuditCase.status),
        AuditCase.opened_at,
        start,
        end,
    )
    cases = dict(db.execute(case_query).all())
    trend_rows = db.execute(
        dated(
            select(func.date(AuditFinding.detected_at).label("day"), func.count().label("count"))
            .where(AuditFinding.organization_id == organization_id)
            .group_by("day"),
            AuditFinding.detected_at,
            start,
            end,
        )
        .order_by(func.date(AuditFinding.detected_at).desc())
        .limit(30)
    ).all()
    suppliers = db.execute(
        select(Supplier.external_id, Supplier.name, func.count(Purchase.id).label("count"))
        .join(
            Purchase,
            (Purchase.organization_id == Supplier.organization_id)
            & (Purchase.supplier_id == Supplier.id),
        )
        .where(*purchase_filter)
        .group_by(Supplier.id, Supplier.external_id, Supplier.name)
        .order_by(func.count(Purchase.id).desc(), Supplier.external_id)
        .limit(10)
    ).all()
    products = db.execute(
        select(
            Purchase.product_id,
            func.max(Purchase.product_name),
            func.count(Purchase.id).label("count"),
        )
        .where(*purchase_filter)
        .group_by(Purchase.product_id)
        .order_by(func.count(Purchase.id).desc(), Purchase.product_id)
        .limit(10)
    ).all()
    return {
        "imports": imports,
        "analyzed_records": analyzed_records,
        "audits": len(runs),
        "findings_by_severity": findings_by_severity,
        "pending_cases": cases.get("open", 0) + cases.get("in_review", 0),
        "resolved_cases": cases.get("resolved", 0),
        "dismissed_cases": cases.get("dismissed", 0),
        "trend": [{"date": str(day), "count": count} for day, count in reversed(trend_rows)],
        "suppliers": [
            {"supplier_id": supplier_id, "name": name, "count": count}
            for supplier_id, name, count in suppliers
        ],
        "products": [
            {"product_id": product_id, "name": name, "count": count}
            for product_id, name, count in products
        ],
        "categories": [],
        "limitations": ["A importação não contém categoria; ranking por produto disponível."],
    }
