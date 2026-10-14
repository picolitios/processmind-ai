import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import and_, or_, select

from app.core.errors import ApiError
from app.features.audit.models import AuditFinding
from app.features.audit.routes import make_cursor
from app.features.cases.models import AuditCase, CaseComment
from app.features.identity.models import AuditEvent, Membership
from app.features.identity.routes import log_event, parse_cursor, require_membership
from app.features.identity.security import DB, Auth, CsrfAuth

router = APIRouter(prefix="/api/v1/organizations/{organization_id}")
WRITERS = {"owner", "admin", "analyst"}
CaseStatus = Literal["open", "in_review", "resolved", "dismissed"]
ReviewState = Literal["in_review", "resolved", "dismissed"]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: uuid.UUID
    assignee_user_id: uuid.UUID | None = None


class CasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: CaseStatus | None = None
    assignee_user_id: uuid.UUID | None = None
    closure_reason: Reason | None = None


class CommentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class FindingReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_state: ReviewState
    reason: Reason | None = None


def get_case(db: DB, organization_id: uuid.UUID, case_id: uuid.UUID) -> AuditCase:
    case = db.scalar(
        select(AuditCase).where(
            AuditCase.organization_id == organization_id, AuditCase.id == case_id
        )
    )
    if case is None:
        raise ApiError(404, "not_found", "Caso não encontrado")
    return case


def assignee_membership(db: DB, organization_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    member = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
    )
    if member is None:
        raise ApiError(422, "invalid_assignee", "Responsável não pertence à organização")
    return member


def case_views(db: DB, cases: list[AuditCase]) -> list[dict[str, Any]]:
    member_ids = [case.assignee_membership_id for case in cases if case.assignee_membership_id]
    users = (
        {
            member.id: member.user_id
            for member in db.scalars(
                select(Membership).where(
                    Membership.organization_id == cases[0].organization_id,
                    Membership.id.in_(member_ids),
                )
            )
        }
        if cases and member_ids
        else {}
    )
    return [
        {
            "id": case.id,
            "finding_id": case.finding_id,
            "status": case.status,
            "assignee_user_id": users.get(case.assignee_membership_id)
            if case.assignee_membership_id
            else None,
            "closure_reason": case.closure_reason,
            "opened_at": case.opened_at,
            "closed_at": case.closed_at,
        }
        for case in cases
    ]


def comment_view(comment: CaseComment, author_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": comment.id,
        "case_id": comment.case_id,
        "author_user_id": author_id,
        "body": comment.body,
        "created_at": comment.created_at,
    }


def add_case_event(
    db: DB,
    request: Request,
    case: AuditCase,
    actor_id: uuid.UUID,
    action: str,
    metadata: dict[str, Any],
) -> None:
    db.add(
        AuditEvent(
            organization_id=case.organization_id,
            actor_user_id=actor_id,
            action=action,
            subject_type="case",
            subject_id=case.id,
            metadata_json=metadata,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )


@router.patch("/findings/{finding_id}", tags=["findings"])
def review_finding(
    organization_id: uuid.UUID,
    finding_id: uuid.UUID,
    data: FindingReviewInput,
    request: Request,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    finding = db.scalar(
        select(AuditFinding)
        .where(
            AuditFinding.organization_id == organization_id,
            AuditFinding.id == finding_id,
        )
        .with_for_update()
    )
    if finding is None:
        raise ApiError(404, "not_found", "Achado não encontrado")
    if (
        db.scalar(
            select(AuditCase.id).where(
                AuditCase.organization_id == organization_id,
                AuditCase.finding_id == finding_id,
            )
        )
        is not None
    ):
        raise ApiError(409, "case_controls_review", "A revisão deste achado pertence ao caso")
    allowed = {
        "unreviewed": {"in_review", "resolved", "dismissed"},
        "in_review": {"resolved", "dismissed"},
    }
    if data.review_state not in allowed.get(finding.review_state, set()):
        raise ApiError(409, "invalid_transition", "Transição de revisão inválida")
    if data.review_state in {"resolved", "dismissed"} and data.reason is None:
        raise ApiError(422, "closure_reason_required", "Justificativa obrigatória")
    previous = finding.review_state
    finding.review_state = data.review_state
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=auth.user.id,
            action="finding.reviewed",
            subject_type="finding",
            subject_id=finding.id,
            metadata_json={"from": previous, "to": data.review_state, "reason": data.reason},
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    db.commit()
    from app.features.audit.routes import get_finding

    return get_finding(organization_id, finding_id, db, auth)


@router.get("/cases", tags=["cases"])
def list_cases(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    status: CaseStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    query = select(AuditCase).where(AuditCase.organization_id == organization_id)
    if status:
        query = query.where(AuditCase.status == status)
    if cursor:
        when, item_id = parse_cursor(cursor)
        query = query.where(
            or_(
                AuditCase.opened_at < when,
                and_(AuditCase.opened_at == when, AuditCase.id < item_id),
            )
        )
    cases = db.scalars(
        query.order_by(AuditCase.opened_at.desc(), AuditCase.id.desc()).limit(limit + 1)
    ).all()
    page = cases[:limit]
    return {
        "items": case_views(db, list(page)),
        "next_cursor": make_cursor(page[-1].opened_at, page[-1].id) if len(cases) > limit else None,
    }


@router.post("/cases", tags=["cases"], status_code=201)
def create_case(
    organization_id: uuid.UUID, data: CaseInput, request: Request, db: DB, auth: CsrfAuth
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS, for_update=True)
    finding = db.scalar(
        select(AuditFinding)
        .where(
            AuditFinding.organization_id == organization_id,
            AuditFinding.id == data.finding_id,
        )
        .with_for_update()
    )
    if finding is None:
        raise ApiError(422, "invalid_finding", "Achado inexistente")
    if finding.review_state in {"resolved", "dismissed"}:
        raise ApiError(409, "finding_closed", "Achado encerrado")
    if (
        db.scalar(
            select(AuditCase.id).where(
                AuditCase.organization_id == organization_id,
                AuditCase.finding_id == finding.id,
            )
        )
        is not None
    ):
        raise ApiError(409, "case_exists", "Este achado já possui um caso")
    assignee = (
        assignee_membership(db, organization_id, data.assignee_user_id)
        if data.assignee_user_id
        else None
    )
    case = AuditCase(
        organization_id=organization_id,
        finding_id=finding.id,
        assignee_membership_id=assignee.id if assignee else None,
        status="open",
    )
    db.add(case)
    db.flush()
    finding.review_state = "in_review"
    log_event(db, request, "case.opened", auth.user.id, "case", case.id, organization_id)
    db.commit()
    return case_views(db, [case])[0]


@router.get("/cases/{case_id}", tags=["cases"])
def case_detail(
    organization_id: uuid.UUID, case_id: uuid.UUID, db: DB, auth: Auth
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    case = get_case(db, organization_id, case_id)
    result = case_views(db, [case])[0]
    comments = db.scalars(
        select(CaseComment)
        .where(
            CaseComment.organization_id == organization_id,
            CaseComment.case_id == case_id,
        )
        .order_by(CaseComment.created_at.desc(), CaseComment.id.desc())
        .limit(20)
    ).all()
    authors = {
        member.id: member.user_id
        for member in db.scalars(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.id.in_([comment.author_membership_id for comment in comments]),
            )
        )
    }
    result["comments"] = [
        comment_view(comment, authors[comment.author_membership_id]) for comment in comments
    ]
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.subject_type == "case",
            AuditEvent.subject_id == case_id,
        )
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(50)
    ).all()
    result["history"] = [
        {
            "action": event.action,
            "actor_user_id": event.actor_user_id,
            "occurred_at": event.occurred_at,
            "metadata": event.metadata_json,
        }
        for event in events
    ]
    return result


@router.patch("/cases/{case_id}", tags=["cases"])
def patch_case(
    organization_id: uuid.UUID,
    case_id: uuid.UUID,
    data: CasePatch,
    request: Request,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, WRITERS)
    case = db.scalar(
        select(AuditCase)
        .where(
            AuditCase.organization_id == organization_id,
            AuditCase.id == case_id,
        )
        .with_for_update()
    )
    if case is None:
        raise ApiError(404, "not_found", "Caso não encontrado")
    if case.status in {"resolved", "dismissed"}:
        raise ApiError(409, "case_closed", "Caso encerrado")
    if data.status is None and "assignee_user_id" not in data.model_fields_set:
        raise ApiError(422, "invalid_patch", "Informe status ou responsável")
    if data.status is not None:
        allowed = {
            "open": {"in_review", "resolved", "dismissed"},
            "in_review": {"resolved", "dismissed"},
        }
        if data.status not in allowed[case.status]:
            raise ApiError(409, "invalid_transition", "Transição de caso inválida")
        if data.status in {"resolved", "dismissed"} and data.closure_reason is None:
            raise ApiError(422, "closure_reason_required", "Justificativa obrigatória")
        if data.status == "in_review" and data.closure_reason is not None:
            raise ApiError(422, "invalid_reason", "Justificativa apenas no encerramento")
        previous = case.status
        case.status = data.status
        if data.status in {"resolved", "dismissed"}:
            case.closure_reason = data.closure_reason
            case.closed_at = datetime.now(UTC)
        finding = db.scalar(
            select(AuditFinding)
            .where(
                AuditFinding.organization_id == organization_id,
                AuditFinding.id == case.finding_id,
            )
            .with_for_update()
        )
        if finding is None:
            raise ValueError("case_finding_missing")
        finding.review_state = "in_review" if data.status == "in_review" else data.status
        add_case_event(
            db,
            request,
            case,
            auth.user.id,
            "case.status_changed",
            {"from": previous, "to": data.status},
        )
    elif data.closure_reason is not None:
        raise ApiError(422, "invalid_reason", "Justificativa apenas no encerramento")
    if "assignee_user_id" in data.model_fields_set:
        if data.assignee_user_id is None:
            raise ApiError(422, "invalid_assignee", "Responsável obrigatório")
        assignee = assignee_membership(db, organization_id, data.assignee_user_id)
        previous_assignee = case.assignee_membership_id
        case.assignee_membership_id = assignee.id
        add_case_event(
            db,
            request,
            case,
            auth.user.id,
            "case.assigned",
            {"from": str(previous_assignee) if previous_assignee else None, "to": str(assignee.id)},
        )
    db.commit()
    return case_views(db, [case])[0]


@router.get("/cases/{case_id}/comments", tags=["cases"])
def list_comments(
    organization_id: uuid.UUID,
    case_id: uuid.UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id)
    get_case(db, organization_id, case_id)
    query = select(CaseComment).where(
        CaseComment.organization_id == organization_id,
        CaseComment.case_id == case_id,
    )
    if cursor:
        when, item_id = parse_cursor(cursor)
        query = query.where(
            or_(
                CaseComment.created_at < when,
                and_(CaseComment.created_at == when, CaseComment.id < item_id),
            )
        )
    comments = db.scalars(
        query.order_by(CaseComment.created_at.desc(), CaseComment.id.desc()).limit(limit + 1)
    ).all()
    page = comments[:limit]
    authors = {
        member.id: member.user_id
        for member in db.scalars(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.id.in_([comment.author_membership_id for comment in page]),
            )
        )
    }
    return {
        "items": [comment_view(comment, authors[comment.author_membership_id]) for comment in page],
        "next_cursor": make_cursor(page[-1].created_at, page[-1].id)
        if len(comments) > limit
        else None,
    }


@router.post("/cases/{case_id}/comments", tags=["cases"], status_code=201)
def create_comment(
    organization_id: uuid.UUID,
    case_id: uuid.UUID,
    data: CommentInput,
    request: Request,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, Any]:
    _, member = require_membership(db, auth, organization_id, WRITERS)
    case = get_case(db, organization_id, case_id)
    comment = CaseComment(
        organization_id=organization_id,
        case_id=case.id,
        author_membership_id=member.id,
        body=data.body,
    )
    db.add(comment)
    db.flush()
    log_event(db, request, "case.commented", auth.user.id, "case", case.id, organization_id)
    db.commit()
    return comment_view(comment, auth.user.id)
