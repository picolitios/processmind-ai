"""Select bounded, tenant-scoped audit evidence for an organization chat."""

import json
import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.features.audit.models import AuditFinding, AuditRun, FindingEvidence

MAX_FINDINGS = 20
MAX_EVIDENCE = 50
MAX_EVIDENCE_BYTES = 2048


def build_organization_context(
    db: Session, organization_id: uuid.UUID, question: str,
) -> tuple[dict[str, Any], set[uuid.UUID], bool]:
    """Rank matching completed findings, then fill with recent ones."""
    document = func.to_tsvector(
        "portuguese",
        func.coalesce(AuditFinding.rule_code, "") + " "
        + func.coalesce(AuditFinding.explanation, ""),
    )
    needle = func.plainto_tsquery("portuguese", question[:300])
    base = (
        select(AuditFinding)
        .join(AuditRun, and_(
            AuditRun.organization_id == AuditFinding.organization_id,
            AuditRun.id == AuditFinding.run_id,
        ))
        .where(
            AuditFinding.organization_id == organization_id,
            AuditRun.status == "succeeded",
        )
    )
    matched = db.scalars(
        base.where(document.op("@@")(needle))
        .order_by(func.ts_rank(document, needle).desc(), AuditFinding.detected_at.desc())
        .limit(MAX_FINDINGS + 1)
    ).all()
    recent = db.scalars(
        base.order_by(AuditFinding.detected_at.desc(), AuditFinding.id.desc())
        .limit(MAX_FINDINGS + 1)
    ).all()
    selected: list[AuditFinding] = []
    seen: set[uuid.UUID] = set()
    candidates = [*matched, *recent]
    for finding in candidates:
        if finding.id not in seen and len(selected) < MAX_FINDINGS:
            selected.append(finding)
            seen.add(finding.id)
    partial = (
        len(matched) > MAX_FINDINGS or len(recent) > MAX_FINDINGS
        or len({item.id for item in candidates}) > MAX_FINDINGS
    )
    if not selected:
        return {"findings": []}, set(), partial

    evidence = db.scalars(
        select(FindingEvidence)
        .where(
            FindingEvidence.organization_id == organization_id,
            FindingEvidence.finding_id.in_([finding.id for finding in selected]),
        )
        .order_by(FindingEvidence.finding_id, FindingEvidence.id)
        .limit(MAX_EVIDENCE + 1)
    ).all()
    partial = partial or len(evidence) > MAX_EVIDENCE
    grouped: dict[uuid.UUID, list[dict[str, Any]]] = {item.id: [] for item in selected}
    allowed: set[uuid.UUID] = set()
    for item in evidence[:MAX_EVIDENCE]:
        encoded = json.dumps(item.evidence_json, ensure_ascii=False, sort_keys=True, default=str)
        truncated = len(encoded.encode("utf-8")) > MAX_EVIDENCE_BYTES
        partial = partial or truncated
        grouped[item.finding_id].append({
            "id": str(item.id),
            "data": {"truncated": True} if truncated else item.evidence_json,
        })
        allowed.add(item.id)
    return {
        "findings": [
            {
                "id": str(item.id),
                "audit_id": str(item.run_id),
                "rule_code": item.rule_code,
                "severity": item.severity,
                "explanation": item.explanation[:1200],
                "evidence": grouped[item.id],
            }
            for item in selected
        ]
    }, allowed, partial
