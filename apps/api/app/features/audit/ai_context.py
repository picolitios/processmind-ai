import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.features.audit.evidence import duplicate_purchase_facts, evidence_data
from app.features.audit.models import AuditFinding, AuditRun, FindingEvidence


def validate_ai_target(
    db: Session, organization_id: uuid.UUID, finding_id: uuid.UUID | None, run_id: uuid.UUID | None
) -> None:
    if finding_id is not None:
        finding = db.scalar(
            select(AuditFinding).where(
                AuditFinding.organization_id == organization_id,
                AuditFinding.id == finding_id,
            )
        )
        if finding is None:
            raise ApiError(422, "invalid_target", "Achado inexistente")
        run_id = finding.run_id
    run = db.scalar(
        select(AuditRun).where(
            AuditRun.organization_id == organization_id,
            AuditRun.id == run_id,
            AuditRun.status == "succeeded",
        )
    )
    if run is None:
        raise ApiError(422, "invalid_target", "Auditoria inexistente ou não concluída")


def build_ai_context(
    db: Session, organization_id: uuid.UUID, finding_id: uuid.UUID | None, run_id: uuid.UUID | None
) -> tuple[dict[str, Any], set[uuid.UUID], bool]:
    query = select(AuditFinding).where(AuditFinding.organization_id == organization_id)
    if finding_id is not None:
        query = query.where(AuditFinding.id == finding_id)
    else:
        query = query.where(AuditFinding.run_id == run_id)
    findings = db.scalars(query.order_by(AuditFinding.id).limit(21)).all()
    selected = findings[:20]
    if not selected:
        return {}, set(), False
    evidence = db.scalars(
        select(FindingEvidence)
        .where(
            FindingEvidence.organization_id == organization_id,
            FindingEvidence.finding_id.in_([finding.id for finding in selected]),
        )
        .order_by(FindingEvidence.finding_id, FindingEvidence.id)
        .limit(51)
    ).all()
    partial = len(findings) > 20 or len(evidence) > 50
    evidence = evidence[:50]
    allowed = {item.id for item in evidence}
    findings_by_id = {item.id: item for item in selected}
    purchase_facts = duplicate_purchase_facts(db, organization_id, selected, evidence)
    grouped: dict[uuid.UUID, list[dict[str, Any]]] = {item.id: [] for item in selected}
    for item in evidence:
        selected_data = evidence_data(findings_by_id[item.finding_id], item, purchase_facts)
        data = json.dumps(selected_data, ensure_ascii=False, sort_keys=True, default=str)
        truncated = len(data.encode("utf-8")) > 2048
        grouped[item.finding_id].append(
            {
                "id": str(item.id),
                "data": {"truncated": True} if truncated else selected_data,
            }
        )
        partial = partial or truncated
    context = {
        "findings": [
            {
                "id": str(item.id),
                "rule_code": item.rule_code,
                "severity": item.severity,
                "explanation": item.explanation[:1200],
                "evidence": grouped[item.id],
            }
            for item in selected
        ]
    }
    return context, allowed, partial
