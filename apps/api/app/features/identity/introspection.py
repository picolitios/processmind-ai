import hashlib
import hmac
import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.core.errors import ApiError
from app.features.identity.models import Membership, User
from app.features.identity.routes import require_membership
from app.features.identity.security import DB, authenticate_token, digest

router = APIRouter(prefix="/internal/v1", include_in_schema=False)


class IntrospectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_token: str = Field(min_length=1, max_length=256)
    csrf_token: str | None = Field(default=None, max_length=256)


class IntrospectionResult(BaseModel):
    user_id: uuid.UUID
    session_id: uuid.UUID
    csrf_valid: bool


class MembershipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_token: str = Field(min_length=1, max_length=256)
    organization_id: uuid.UUID


class MembershipResult(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: Literal["owner", "admin", "analyst", "viewer"]


class MemberReferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_token: str = Field(min_length=1, max_length=256)
    organization_id: uuid.UUID
    membership_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    user_id: uuid.UUID | None = None


class MemberReference(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    status: Literal["active", "inactive"]
    display_name: str | None = None
    email: str | None = None


class MemberReferencesResult(BaseModel):
    organization_id: uuid.UUID
    members: list[MemberReference]


def signature(
    timestamp: str, session_token: str, csrf_token: str | None,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Bind optional request correlation to the existing private-call HMAC."""
    message = f"{timestamp}\n{session_token}\n{csrf_token or ''}"
    if correlation_id is not None:
        message += f"\n{correlation_id}"
    encoded = message.encode()
    return hmac.new(settings.auth_hash_key.encode(), encoded, hashlib.sha256).hexdigest()


def member_references_subject(
    organization_id: uuid.UUID, membership_ids: list[uuid.UUID], user_id: uuid.UUID | None,
    user_ids: list[uuid.UUID] | None = None,
) -> str:
    # Canonical ordering binds the HMAC to every requested reference, independent of list order.
    members = ",".join(sorted(str(member_id) for member_id in membership_ids))
    requested_users = ",".join(sorted(str(item) for item in (user_ids or [])))
    return f"member-refs:{organization_id}:{user_id or ''}:{members}:{requested_users}"


def verify_internal_signature(
    timestamp: str, supplied: str, token: str, subject: str | None,
    request: Request | None = None, correlation_id: uuid.UUID | None = None,
) -> None:
    try:
        issued_at = int(timestamp)
    except ValueError as exc:
        raise ApiError(403, "forbidden", "Serviço não autorizado") from exc
    valid_signature = len(supplied) == 64 and hmac.compare_digest(
        supplied, signature(timestamp, token, subject, correlation_id)
    )
    if abs(time.time() - issued_at) > 30 or not valid_signature:
        raise ApiError(403, "forbidden", "Serviço não autorizado")
    if request is not None and correlation_id is not None:
        request.state.correlation_id = str(correlation_id)


@router.post("/session/introspect", response_model=IntrospectionResult)
def introspect(
    data: IntrospectionInput,
    db: DB,
    request: Request,
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
    x_internal_correlation_id: Annotated[uuid.UUID | None, Header()] = None,
) -> IntrospectionResult:
    verify_internal_signature(
        x_internal_timestamp, x_internal_signature, data.session_token, data.csrf_token,
        request, x_internal_correlation_id,
    )
    auth = authenticate_token(db, data.session_token)
    csrf_valid = data.csrf_token is not None and hmac.compare_digest(
        digest(data.csrf_token), auth.session.csrf_hash
    )
    return IntrospectionResult(
        user_id=auth.user.id, session_id=auth.session.id, csrf_valid=csrf_valid
    )


@router.post("/membership/authorize", response_model=MembershipResult)
def authorize_membership(
    data: MembershipInput,
    db: DB,
    request: Request,
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
    x_internal_correlation_id: Annotated[uuid.UUID | None, Header()] = None,
) -> MembershipResult:
    verify_internal_signature(
        x_internal_timestamp,
        x_internal_signature,
        data.session_token,
        f"membership:{data.organization_id}",
        request,
        x_internal_correlation_id,
    )
    auth = authenticate_token(db, data.session_token)
    _, member = require_membership(db, auth, data.organization_id)
    return MembershipResult(
        membership_id=member.id,
        user_id=member.user_id,
        organization_id=member.organization_id,
        role=member.role,
    )


@router.post("/membership/references", response_model=MemberReferencesResult)
def resolve_member_references(
    data: MemberReferencesInput,
    db: DB,
    request: Request,
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
    x_internal_correlation_id: Annotated[uuid.UUID | None, Header()] = None,
) -> MemberReferencesResult:
    # The signed subject prevents changing the tenant or requested IDs after authorization.
    verify_internal_signature(
        x_internal_timestamp,
        x_internal_signature,
        data.session_token,
        member_references_subject(
            data.organization_id, data.membership_ids, data.user_id, data.user_ids
        ),
        request,
        x_internal_correlation_id,
    )
    auth = authenticate_token(db, data.session_token)
    require_membership(db, auth, data.organization_id)
    filters: list[ColumnElement[bool]] = []
    if data.membership_ids:
        filters.append(Membership.id.in_(data.membership_ids))
    if data.user_id is not None:
        filters.append(Membership.user_id == data.user_id)
    if data.user_ids:
        filters.append(Membership.user_id.in_(data.user_ids))
    members = (
        db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == data.organization_id, or_(*filters))
        ).all()
        if filters
        else []
    )
    return MemberReferencesResult(
        organization_id=data.organization_id,
        members=[
            MemberReference(
                membership_id=member.id, user_id=member.user_id, status=member.status,
                display_name=user.display_name, email=user.email,
            )
            for member, user in members
        ],
    )
