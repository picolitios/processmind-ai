import uuid
from typing import Any

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ApiError
from app.features.ai.models import AIAnalysis
from app.features.ai.schemas import AIInput
from app.features.audit.ai_context import validate_ai_target
from app.features.identity.routes import log_event, require_membership
from app.features.identity.security import DB, Auth, CsrfAuth
from app.features.ingestion.models import Job

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/ai", tags=["ai"])
WRITERS = {"owner", "admin", "analyst"}


def analysis_view(analysis: AIAnalysis) -> dict[str, Any]:
    result = analysis.response_json or {}
    return {
        "id": analysis.id,
        "status": analysis.status,
        "summary": result.get("summary"),
        "possible_causes": result.get("possible_causes", []),
        "suggested_checks": result.get("suggested_checks", []),
        "corrective_actions": result.get("corrective_actions", []),
        "evidence_ids": result.get("evidence_ids", []),
        "limitation": analysis.limitation,
    }


@router.post("/analyses", status_code=202)
def create_analysis(
    organization_id: uuid.UUID,
    data: AIInput,
    request: Request,
    db: DB,
    auth: CsrfAuth,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS, for_update=True)
    prior = db.scalar(
        select(AIAnalysis).where(
            AIAnalysis.organization_id == organization_id,
            AIAnalysis.idempotency_key == idempotency_key,
        )
    )
    if prior is not None:
        if prior.finding_id != data.finding_id or prior.run_id != data.audit_id:
            raise ApiError(409, "idempotency_conflict", "Chave usada com outro alvo")
        return {"id": prior.job_id, "analysis_id": prior.id, "status": prior.status}
    validate_ai_target(db, organization_id, data.finding_id, data.audit_id)
    analysis = AIAnalysis(
        organization_id=organization_id,
        requester_id=auth.user.id,
        run_id=data.audit_id,
        finding_id=data.finding_id,
        idempotency_key=idempotency_key,
        model=settings.ollama_model,
        status="queued",
    )
    db.add(analysis)
    db.flush()
    job = Job(
        organization_id=organization_id,
        type="ai",
        status="queued",
        payload_json={"analysis_id": str(analysis.id)},
        idempotency_key=str(analysis.id),
    )
    db.add(job)
    db.flush()
    analysis.job_id = job.id
    log_event(db, request, "ai.queued", auth.user.id, "ai_analysis", analysis.id, organization_id)
    db.commit()
    return {"id": job.id, "analysis_id": analysis.id, "status": job.status}


@router.get("/analyses/{analysis_id}")
def get_analysis(
    organization_id: uuid.UUID,
    analysis_id: uuid.UUID,
    db: DB,
    auth: Auth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    analysis = db.scalar(
        select(AIAnalysis).where(
            AIAnalysis.organization_id == organization_id,
            AIAnalysis.id == analysis_id,
        )
    )
    if analysis is None:
        raise ApiError(404, "not_found", "Análise não encontrada")
    return analysis_view(analysis)
