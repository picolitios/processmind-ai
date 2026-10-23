import base64
import json
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.errors import ApiError
from app.features.audit.evidence import duplicate_purchase_facts, evidence_data
from app.features.audit.models import AuditConfiguration, AuditFinding, AuditRun, FindingEvidence
from app.features.audit.outbox import OutboxEvent
from app.features.audit.rules import RULE_VERSION
from app.features.audit_trail.events import log_business_event as log_event
from app.features.identity.client import BusinessAuth as Auth
from app.features.identity.client import BusinessCsrfAuth as CsrfAuth
from app.features.identity.client import require_business_membership as require_membership
from app.features.identity.routes import parse_cursor
from app.features.identity.security import DB
from app.features.ingestion.models import ImportBatch, Job

router = APIRouter(prefix="/api/v1/organizations/{organization_id}")
WRITERS = {"owner", "admin", "analyst"}


class AuditInput(BaseModel):
    import_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


def audit_view(run: AuditRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "rule_set_version": run.rule_set_version,
        "finding_count": run.finding_count,
        "limitation": run.limitation,
        "job_id": run.job_id,
        "import_ids": run.import_ids,
    }


def get_run(db: DB, organization_id: uuid.UUID, audit_id: uuid.UUID) -> AuditRun:
    run = db.scalar(
        select(AuditRun).where(
            AuditRun.organization_id == organization_id,
            AuditRun.id == audit_id,
        )
    )
    if run is None:
        raise ApiError(404, "not_found", "Auditoria não encontrada")
    return run


def make_cursor(when: datetime, item_id: uuid.UUID) -> str:
    value = json.dumps({"created_at": when.isoformat(), "id": str(item_id)})
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def finding_view(
    finding: AuditFinding,
    evidence: Sequence[FindingEvidence],
    purchase_facts: dict[uuid.UUID, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": finding.id,
        "audit_id": finding.run_id,
        "rule_code": finding.rule_code,
        "rule_version": finding.rule_version,
        "severity": finding.severity,
        "review_state": finding.review_state,
        "detected_at": finding.detected_at,
        "explanation": finding.explanation,
        "evidence": [
            {
                "id": item.id,
                "type": "purchase" if item.purchase_id else "import_row",
                "purchase_id": item.purchase_id,
                "import_row_id": item.import_row_id,
                "data": evidence_data(finding, item, purchase_facts),
            }
            for item in evidence
        ],
    }


@router.post("/audits", tags=["audits"], status_code=202)
def create_audit(
    organization_id: uuid.UUID,
    data: AuditInput,
    request: Request,
    db: DB,
    auth: CsrfAuth,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> dict[str, Any]:
    org, _ = require_membership(db, auth, organization_id, WRITERS, for_update=True)
    import_ids = sorted(set(data.import_ids))
    if len(import_ids) != len(data.import_ids):
        raise ApiError(422, "invalid_imports", "Importações repetidas")
    prior = db.scalar(
        select(AuditRun).where(
            AuditRun.organization_id == organization_id,
            AuditRun.idempotency_key == idempotency_key,
        )
    )
    if prior is not None:
        if prior.import_ids != [str(item) for item in import_ids]:
            raise ApiError(409, "idempotency_conflict", "Chave usada com outras importações")
        return audit_view(prior)
    batches = db.scalars(
        select(ImportBatch).where(
            ImportBatch.organization_id == organization_id,
            ImportBatch.id.in_(import_ids),
            ImportBatch.status == "succeeded",
        )
    ).all()
    if len(batches) != len(import_ids):
        raise ApiError(422, "invalid_imports", "Importações inexistentes ou não concluídas")
    if settings.audit_config_mode == "owned":
        # The audit-owned row serializes settings apply and snapshot creation.
        audit_config = db.get(AuditConfiguration, organization_id, with_for_update=True)
        if audit_config is None:
            raise ApiError(
                503, "audit_configuration_missing", "Configuração de auditoria indisponível"
            )
        snapshot = {
            "settings_version": audit_config.settings_version,
            "amount_limits": audit_config.amount_limits,
            "delay_window_days": audit_config.delay_window_days,
        }
    else:
        if org is None:
            raise ApiError(
                503, "audit_configuration_missing", "Configuração de auditoria indisponível"
            )
        snapshot = {
            "settings_version": org.settings_version,
            "amount_limits": org.settings.get("amount_limits", {}),
            "delay_window_days": org.settings.get("delay_window_days", 90),
        }
    run = AuditRun(
        organization_id=organization_id,
        requester_id=auth.user.id,
        status="queued",
        rule_set_version=RULE_VERSION,
        config_snapshot=snapshot,
        import_ids=[str(item) for item in import_ids],
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.flush()
    job = Job(
        organization_id=organization_id,
        type="audit",
        status="queued",
        payload_json={"audit_id": str(run.id)},
        idempotency_key=str(run.id),
    )
    db.add(job)
    db.flush()
    run.job_id = job.id
    if settings.audit_dispatch_mode == "broker":
        event_id = uuid.uuid4()
        db.add(
            OutboxEvent(
                id=event_id,
                organization_id=organization_id,
                event_type="audit.requested",
                event_version=1,
                envelope={
                    "event_id": str(event_id),
                    "event_type": "audit.requested",
                    "event_version": 1,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "correlation_id": request.state.correlation_id,
                    "causation_id": None,
                    "tenant_id": str(organization_id),
                    "payload": {"audit_id": str(run.id), "job_id": str(job.id)},
                },
            )
        )
    log_event(db, request, "audit.queued", auth.user.id, "audit", run.id, organization_id)
    db.commit()
    return audit_view(run)


@router.get("/audits", tags=["audits"])
def list_audits(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    statement = select(AuditRun).where(AuditRun.organization_id == organization_id)
    if cursor:
        timestamp, item_id = parse_cursor(cursor)
        statement = statement.where(
            or_(
                AuditRun.created_at < timestamp,
                and_(AuditRun.created_at == timestamp, AuditRun.id < item_id),
            )
        )
    runs = db.scalars(
        statement.order_by(AuditRun.created_at.desc(), AuditRun.id.desc()).limit(limit + 1)
    ).all()
    page = runs[:limit]
    return {
        "items": [audit_view(item) for item in page],
        "next_cursor": make_cursor(page[-1].created_at, page[-1].id) if len(runs) > limit else None,
    }


@router.get("/audits/{audit_id}", tags=["audits"])
def get_audit(
    organization_id: uuid.UUID,
    audit_id: uuid.UUID,
    db: DB,
    auth: Auth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    return audit_view(get_run(db, organization_id, audit_id))


@router.get("/findings", tags=["findings"])
def list_findings(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    audit_id: uuid.UUID | None = None,
    severity: Literal["low", "medium", "high", "critical"] | None = None,
    review_state: Literal["unreviewed", "in_review", "resolved", "dismissed"] | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    query = select(AuditFinding).where(AuditFinding.organization_id == organization_id)
    if audit_id:
        query = query.where(AuditFinding.run_id == audit_id)
    if severity:
        query = query.where(AuditFinding.severity == severity)
    if review_state:
        query = query.where(AuditFinding.review_state == review_state)
    if cursor:
        timestamp, item_id = parse_cursor(cursor)
        query = query.where(
            or_(
                AuditFinding.detected_at > timestamp,
                and_(AuditFinding.detected_at == timestamp, AuditFinding.id > item_id),
            )
        )
    findings = db.scalars(
        query.order_by(AuditFinding.detected_at, AuditFinding.id).limit(limit + 1)
    ).all()
    page = findings[:limit]
    evidence_by_finding: dict[uuid.UUID, list[FindingEvidence]] = defaultdict(list)
    if page:
        for item in db.scalars(
            select(FindingEvidence)
            .where(
                FindingEvidence.organization_id == organization_id,
                FindingEvidence.finding_id.in_([finding.id for finding in page]),
            )
            .order_by(FindingEvidence.id)
        ):
            evidence_by_finding[item.finding_id].append(item)
    page_evidence = [item for group in evidence_by_finding.values() for item in group]
    purchase_facts = duplicate_purchase_facts(db, organization_id, page, page_evidence)
    return {
        "items": [
            finding_view(item, evidence_by_finding[item.id], purchase_facts) for item in page
        ],
        "next_cursor": make_cursor(page[-1].detected_at, page[-1].id)
        if len(findings) > limit
        else None,
    }


@router.get("/findings/{finding_id}", tags=["findings"])
def get_finding(
    organization_id: uuid.UUID,
    finding_id: uuid.UUID,
    db: DB,
    auth: Auth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    finding = db.scalar(
        select(AuditFinding).where(
            AuditFinding.organization_id == organization_id,
            AuditFinding.id == finding_id,
        )
    )
    if finding is None:
        raise ApiError(404, "not_found", "Achado não encontrado")
    evidence = db.scalars(
        select(FindingEvidence)
        .where(
            FindingEvidence.organization_id == organization_id,
            FindingEvidence.finding_id == finding.id,
        )
        .order_by(FindingEvidence.id)
    ).all()
    purchase_facts = duplicate_purchase_facts(db, organization_id, [finding], evidence)
    return finding_view(finding, evidence, purchase_facts)
