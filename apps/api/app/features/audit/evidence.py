"""Resolve purchase facts for finding labels and duplicate comparisons."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.features.audit.models import AuditFinding, FindingEvidence
from app.features.ingestion.models import Purchase, Supplier


def purchase_facts_for_evidence(
    db: Session,
    organization_id: uuid.UUID,
    findings: Sequence[AuditFinding],
    evidence: Sequence[FindingEvidence],
) -> dict[uuid.UUID, dict[str, Any]]:
    """Fetch linked purchases in one tenant-scoped query, including older findings."""
    finding_ids = {finding.id for finding in findings}
    purchase_ids = {
        item.purchase_id
        for item in evidence
        if item.finding_id in finding_ids and item.purchase_id is not None
    }
    if not purchase_ids:
        return {}
    rows = db.execute(
        select(Purchase, Supplier.external_id, Supplier.name)
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
            "supplier_name": supplier_name,
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
        for purchase, supplier_id, supplier_name in rows
    }


def finding_subject(
    finding: AuditFinding,
    evidence: Sequence[FindingEvidence],
    purchase_facts: dict[uuid.UUID, dict[str, Any]],
) -> tuple[str, str]:
    """Label the analyzed product, supplier, or invalid source row for grouping."""
    facts = [
        purchase_facts[item.purchase_id]
        for item in evidence
        if item.purchase_id in purchase_facts
    ]
    if facts:
        first = facts[0]
        if finding.rule_code == "RECURRING_DELAY":
            supplier_id = first["supplier_id"]
            supplier_name = first["supplier_name"] or supplier_id
            return f"supplier:{supplier_id}", f"Fornecedor {supplier_name}"
        product_id = first["product_id"]
        product_name = first["product_name"] or product_id
        return f"product:{product_id}", f"{product_name} ({product_id})"
    if evidence:
        first_row = evidence[0]
        row_number = first_row.evidence_json.get("row_number")
        label = f"Linha {row_number} da importação" if row_number else "Linha da importação"
        return f"row:{first_row.import_row_id}", label
    return f"finding:{finding.id}", "Item não identificado"


def evidence_data(
    finding: AuditFinding,
    item: FindingEvidence,
    purchase_facts: dict[uuid.UUID, dict[str, Any]],
) -> dict[str, Any]:
    """Enrich duplicate evidence at read time while preserving the original audit record."""
    if finding.rule_code == "DUPLICATE" and item.purchase_id in purchase_facts:
        return {**item.evidence_json, "purchase": purchase_facts[item.purchase_id]}
    return item.evidence_json
