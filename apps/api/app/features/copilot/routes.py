import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, Query
from sqlalchemy import and_, or_, select

from app.core.errors import ApiError
from app.features.audit.ai_context import validate_ai_target
from app.features.audit.models import AuditFinding, FindingEvidence
from app.features.audit.routes import make_cursor
from app.features.copilot.models import CopilotConversation, CopilotPolicy, CopilotTurn
from app.features.copilot.schemas import ConversationInput, PolicyInput, QuestionInput
from app.features.identity.client import BusinessAuth as Auth
from app.features.identity.client import BusinessCsrfAuth as CsrfAuth
from app.features.identity.client import require_business_membership as require_membership
from app.features.identity.routes import parse_cursor
from app.features.identity.security import DB
from app.features.ingestion.models import Job

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/ai/copilot", tags=["copilot"])
WRITERS = {"owner", "admin", "analyst"}
MANAGERS = {"owner", "admin"}
TEMPORARY_LIFETIME = timedelta(hours=1)


def policy_view(policy: CopilotPolicy | None) -> dict[str, Any]:
    """Return the documented defaults when no policy row exists."""
    return {
        "temporary_default": policy.temporary_default if policy else False,
        "memory_turn_limit": policy.memory_turn_limit if policy else 10,
    }


def conversation_view(conversation: CopilotConversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "finding_id": conversation.finding_id,
        "audit_id": conversation.run_id,
        "mode": conversation.mode,
        "status": conversation.status,
        "created_at": conversation.created_at,
        "expires_at": conversation.expires_at,
    }


def active_conversation(
    db: DB, organization_id: uuid.UUID, conversation_id: uuid.UUID, author_id: uuid.UUID,
    *, lock: bool = False,
) -> CopilotConversation:
    """Never resolve a conversation outside its tenant and author boundary."""
    query = select(CopilotConversation).where(
        CopilotConversation.organization_id == organization_id,
        CopilotConversation.id == conversation_id,
        CopilotConversation.author_id == author_id,
    )
    if lock:
        query = query.with_for_update()
    conversation = db.scalar(query)
    if conversation is None or (
        conversation.expires_at is not None
        and conversation.expires_at <= datetime.now(UTC)
    ):
        raise ApiError(404, "not_found", "Conversa não encontrada")
    return conversation


def turn_views(db: DB, turns: list[CopilotTurn]) -> list[dict[str, Any]]:
    """Resolve all navigation citations in one tenant-scoped query."""
    if not turns:
        return []
    ids = {uuid.UUID(value) for turn in turns for value in turn.evidence_ids}
    citations: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
    if ids:
        rows = db.execute(
            select(FindingEvidence.id, FindingEvidence.finding_id, AuditFinding.run_id)
            .join(
                AuditFinding,
                and_(
                    AuditFinding.organization_id == FindingEvidence.organization_id,
                    AuditFinding.id == FindingEvidence.finding_id,
                ),
            )
            .where(
                FindingEvidence.organization_id == turns[0].organization_id,
                FindingEvidence.id.in_(ids),
            )
        ).all()
        citations = {
            evidence_id: {
                "evidence_id": evidence_id,
                "finding_id": finding_id,
                "audit_id": run_id,
            }
            for evidence_id, finding_id, run_id in rows
        }
    return [
        {
            "id": turn.id,
            "conversation_id": turn.conversation_id,
            "status": turn.status,
            "question": turn.question,
            "answer": turn.answer,
            "citations": [
                citations[uuid.UUID(value)]
                for value in turn.evidence_ids
                if uuid.UUID(value) in citations
            ],
            "limitation": turn.limitation,
            "created_at": turn.created_at,
        }
        for turn in turns
    ]


@router.get("/policy")
def get_policy(organization_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    return policy_view(db.get(CopilotPolicy, organization_id))


@router.put("/policy")
def put_policy(
    organization_id: uuid.UUID, data: PolicyInput, db: DB, auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, MANAGERS)
    policy = db.get(CopilotPolicy, organization_id)
    if policy is None:
        policy = CopilotPolicy(organization_id=organization_id)
        db.add(policy)
    policy.temporary_default = data.temporary_default
    policy.memory_turn_limit = data.memory_turn_limit
    db.commit()
    return policy_view(policy)


@router.post("/conversations", status_code=201)
def create_conversation(
    organization_id: uuid.UUID, data: ConversationInput, db: DB, auth: CsrfAuth,
) -> dict[str, Any]:
    _, member = require_membership(db, auth, organization_id, WRITERS)
    validate_ai_target(db, organization_id, data.finding_id, data.audit_id)
    policy = policy_view(db.get(CopilotPolicy, organization_id))
    needs_approval = (
        data.mode == "normal" and policy["temporary_default"] and member.role not in MANAGERS
    )
    conversation = CopilotConversation(
        organization_id=organization_id,
        author_id=auth.user.id,
        finding_id=data.finding_id,
        run_id=data.audit_id,
        mode=data.mode,
        status="pending" if needs_approval else "active",
        decided_by=auth.user.id if data.mode == "normal" and not needs_approval else None,
        expires_at=datetime.now(UTC) + TEMPORARY_LIFETIME
        if data.mode == "temporary" else None,
    )
    db.add(conversation)
    db.commit()
    return conversation_view(conversation)


@router.get("/conversations")
def list_conversations(
    organization_id: uuid.UUID, db: DB, auth: Auth,
    finding_id: uuid.UUID | None = None, audit_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50), cursor: str | None = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    if (finding_id is None) == (audit_id is None):
        raise ApiError(422, "invalid_target", "Informe exatamente um alvo")
    query = select(CopilotConversation).where(
        CopilotConversation.organization_id == organization_id,
        CopilotConversation.author_id == auth.user.id,
        CopilotConversation.mode == "normal",
        CopilotConversation.status != "rejected",
        CopilotConversation.finding_id == finding_id,
        CopilotConversation.run_id == audit_id,
    )
    if cursor:
        when, item_id = parse_cursor(cursor)
        query = query.where(
            or_(
                CopilotConversation.created_at < when,
                and_(CopilotConversation.created_at == when, CopilotConversation.id < item_id),
            )
        )
    rows = db.scalars(
        query.order_by(CopilotConversation.created_at.desc(), CopilotConversation.id.desc())
        .limit(limit + 1)
    ).all()
    page = rows[:limit]
    return {
        "items": [conversation_view(item) for item in page],
        "next_cursor": make_cursor(page[-1].created_at, page[-1].id)
        if len(rows) > limit else None,
    }


@router.get("/approvals")
def list_approvals(
    organization_id: uuid.UUID, db: DB, auth: Auth,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, MANAGERS)
    pending = db.scalars(
        select(CopilotConversation).where(
            CopilotConversation.organization_id == organization_id,
            CopilotConversation.mode == "normal",
            CopilotConversation.status == "pending",
        ).order_by(CopilotConversation.created_at, CopilotConversation.id).limit(limit)
    ).all()
    return {"items": [
        {**conversation_view(item), "author_id": item.author_id} for item in pending
    ]}


def decide_conversation(
    organization_id: uuid.UUID, conversation_id: uuid.UUID,
    decision: str, db: DB, auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, MANAGERS)
    conversation = db.scalar(
        select(CopilotConversation).where(
            CopilotConversation.organization_id == organization_id,
            CopilotConversation.id == conversation_id,
            CopilotConversation.mode == "normal",
        ).with_for_update()
    )
    if conversation is None:
        raise ApiError(404, "not_found", "Conversa não encontrada")
    if conversation.status != "pending" and conversation.status != decision:
        raise ApiError(409, "decision_conflict", "Conversa já decidida")
    if conversation.status == decision:
        return conversation_view(conversation)
    conversation.status = decision
    conversation.decided_by = auth.user.id
    db.commit()
    return conversation_view(conversation)


@router.post("/conversations/{conversation_id}/approve")
def approve_conversation(
    organization_id: uuid.UUID, conversation_id: uuid.UUID, db: DB, auth: CsrfAuth,
) -> dict[str, Any]:
    return decide_conversation(organization_id, conversation_id, "active", db, auth)


@router.post("/conversations/{conversation_id}/reject")
def reject_conversation(
    organization_id: uuid.UUID, conversation_id: uuid.UUID, db: DB, auth: CsrfAuth,
) -> dict[str, Any]:
    return decide_conversation(organization_id, conversation_id, "rejected", db, auth)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    organization_id: uuid.UUID, conversation_id: uuid.UUID, db: DB, auth: Auth,
    limit: int = Query(default=20, ge=1, le=50), cursor: str | None = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    conversation = active_conversation(db, organization_id, conversation_id, auth.user.id)
    query = select(CopilotTurn).where(
        CopilotTurn.organization_id == organization_id,
        CopilotTurn.conversation_id == conversation_id,
    )
    if cursor:
        when, item_id = parse_cursor(cursor)
        query = query.where(
            or_(CopilotTurn.created_at < when,
                and_(CopilotTurn.created_at == when, CopilotTurn.id < item_id))
        )
    rows = db.scalars(
        query.order_by(CopilotTurn.created_at.desc(), CopilotTurn.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    return {
        "conversation": conversation_view(conversation),
        "turns": turn_views(db, list(reversed(page))),
        "next_cursor": make_cursor(page[-1].created_at, page[-1].id)
        if len(rows) > limit else None,
    }


@router.post("/conversations/{conversation_id}/questions", status_code=202)
def ask_question(
    organization_id: uuid.UUID, conversation_id: uuid.UUID, data: QuestionInput,
    db: DB, auth: CsrfAuth,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    conversation = active_conversation(
        db, organization_id, conversation_id, auth.user.id, lock=True
    )
    if conversation.status != "active":
        raise ApiError(409, "conversation_not_active", "Conversa aguarda aprovação")
    previous = db.scalar(select(CopilotTurn).where(
        CopilotTurn.organization_id == organization_id,
        CopilotTurn.idempotency_key == idempotency_key,
    ))
    if previous is not None:
        if previous.conversation_id != conversation_id or previous.question != data.question:
            raise ApiError(409, "idempotency_conflict", "Chave usada com outra pergunta")
        return {"question_id": previous.id, "job_id": previous.job_id, "status": previous.status}
    busy = db.scalar(select(CopilotTurn.id).where(
        CopilotTurn.organization_id == organization_id,
        CopilotTurn.conversation_id == conversation_id,
        CopilotTurn.status.in_(("queued", "running")),
    ).limit(1))
    if busy is not None:
        raise ApiError(409, "conversation_busy", "Aguarde a resposta anterior")
    if conversation.mode == "temporary":
        conversation.expires_at = datetime.now(UTC) + TEMPORARY_LIFETIME
    turn = CopilotTurn(
        organization_id=organization_id,
        conversation_id=conversation_id,
        author_id=auth.user.id,
        idempotency_key=idempotency_key,
        question=data.question,
        status="queued",
        expires_at=conversation.expires_at,
    )
    db.add(turn)
    db.flush()
    job = Job(
        organization_id=organization_id,
        type="copilot",
        status="queued",
        payload_json={"turn_id": str(turn.id)},
        idempotency_key=str(turn.id),
    )
    db.add(job)
    db.flush()
    turn.job_id = job.id
    db.commit()
    return {"question_id": turn.id, "job_id": job.id, "status": turn.status}


@router.get("/questions/{question_id}")
def get_question(
    organization_id: uuid.UUID, question_id: uuid.UUID, db: DB, auth: Auth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    turn = db.scalar(select(CopilotTurn).join(
        CopilotConversation,
        and_(CopilotConversation.organization_id == CopilotTurn.organization_id,
             CopilotConversation.id == CopilotTurn.conversation_id),
    ).where(
        CopilotTurn.organization_id == organization_id,
        CopilotTurn.id == question_id,
        CopilotTurn.author_id == auth.user.id,
        or_(CopilotConversation.expires_at.is_(None),
            CopilotConversation.expires_at > datetime.now(UTC)),
    ))
    if turn is None:
        raise ApiError(404, "not_found", "Pergunta não encontrada")
    return turn_views(db, [turn])[0]


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    organization_id: uuid.UUID, conversation_id: uuid.UUID,
    db: DB, auth: CsrfAuth,
) -> None:
    require_membership(db, auth, organization_id, WRITERS)
    conversation = active_conversation(
        db, organization_id, conversation_id, auth.user.id, lock=True
    )
    busy = db.scalar(select(CopilotTurn.id).where(
        CopilotTurn.organization_id == organization_id,
        CopilotTurn.conversation_id == conversation_id,
        CopilotTurn.status.in_(("queued", "running")),
    ).limit(1))
    if busy is not None:
        raise ApiError(409, "conversation_busy", "Aguarde a resposta anterior")
    db.delete(conversation)
    db.commit()
