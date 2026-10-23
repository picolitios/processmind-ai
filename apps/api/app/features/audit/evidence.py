"""Resolve selected purchase facts for duplicate findings without changing stored evidence."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.features.audit.models import AuditFinding, FindingEvidence
from app.features.ingestion.models import Purchase, Supplier


def duplicate_purchase_facts(
    db: Session,
    organization_id: uuid.UUID,
    findings: Sequence[AuditFinding],
    evidence: Sequence[FindingEvidence],
) -> dict[uuid.UUID, dict[str, Any]]:
    """Fetch the compared purchases in one tenant-scoped query, including older findings."""
    duplicate_ids = {finding.id for finding in findings if finding.rule_code == "DUPLICATE"}
    purchase_ids = {
        item.purchase_id
        for item in evidence
        if item.finding_id in duplicate_ids and item.purchase_id is not None
    }
    if not purchase_ids:
        return {}
    rows = db.execute(
        select(Purchase, Supplier.external_id)
        .join(
            Supplier,
            and_(
                Purchase.organization_id == Supplier.organization_id,
                Purchase.supplier_id == Supplier.id,
            ),
        )
        .where(Purchase.organization_id == organization_id, Purchase.id.in_(purchase_ids))
    ).all()
    return {
        purchase.id: {
            "purchase_id": purchase.external_purchase_id,
            "supplier_id": supplier_id,
            "product_id": purchase.product_id,
            "product_name": purchase.product_name,
            "purchase_date": purchase.purchase_date.isoformat(),
            "quantity": str(purchase.quantity),
            "unit_of_measure": purchase.unit_of_measure,
            "unit_price": str(purchase.unit_price),
            "declared_total": str(purchase.declared_total),
            "currency": purchase.currency,
            "import_id": str(purchase.batch_id),
        }
        for purchase, supplier_id in rows
    }


def evidence_data(
    finding: AuditFinding,
    item: FindingEvidence,
    purchase_facts: dict[uuid.UUID, dict[str, Any]],
) -> dict[str, Any]:
    """Enrich duplicate evidence at read time while preserving the original audit record."""
    if finding.rule_code == "DUPLICATE" and item.purchase_id in purchase_facts:
        return {**item.evidence_json, "purchase": purchase_facts[item.purchase_id]}
    return item.evidence_json
