import hashlib
import hmac
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.core.errors import ApiError
from app.features.identity.models import Membership
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
    user_id: uuid.UUID | None = None


class MemberReference(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    status: Literal["active", "inactive"]


class MemberReferencesResult(BaseModel):
    organization_id: uuid.UUID
    members: list[MemberReference]


def signature(timestamp: str, session_token: str, csrf_token: str | None) -> str:
    message = f"{timestamp}\n{session_token}\n{csrf_token or ''}".encode()
    return hmac.new(settings.auth_hash_key.encode(), message, hashlib.sha256).hexdigest()


def member_references_subject(
    organization_id: uuid.UUID, membership_ids: list[uuid.UUID], user_id: uuid.UUID | None
) -> str:
    # Canonical ordering binds the HMAC to every requested reference, independent of list order.
    members = ",".join(sorted(str(member_id) for member_id in membership_ids))
    return f"member-refs:{organization_id}:{user_id or ''}:{members}"


def verify_internal_signature(
    timestamp: str, supplied: str, token: str, subject: str | None
) -> None:
    try:
        issued_at = int(timestamp)
    except ValueError as exc:
        raise ApiError(403, "forbidden", "Serviço não autorizado") from exc
    valid_signature = len(supplied) == 64 and hmac.compare_digest(
        supplied, signature(timestamp, token, subject)
    )
    if abs(time.time() - issued_at) > 30 or not valid_signature:
        raise ApiError(403, "forbidden", "Serviço não autorizado")


@router.post("/session/introspect", response_model=IntrospectionResult)
def introspect(
    data: IntrospectionInput,
    db: DB,
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
) -> IntrospectionResult:
    verify_internal_signature(
        x_internal_timestamp, x_internal_signature, data.session_token, data.csrf_token
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
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
) -> MembershipResult:
    verify_internal_signature(
        x_internal_timestamp,
        x_internal_signature,
        data.session_token,
        f"membership:{data.organization_id}",
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
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
) -> MemberReferencesResult:
    # The signed subject prevents changing the tenant or requested IDs after authorization.
    verify_internal_signature(
        x_internal_timestamp,
        x_internal_signature,
        data.session_token,
        member_references_subject(data.organization_id, data.membership_ids, data.user_id),
    )
    auth = authenticate_token(db, data.session_token)
    require_membership(db, auth, data.organization_id)
    filters: list[ColumnElement[bool]] = []
    if data.membership_ids:
        filters.append(Membership.id.in_(data.membership_ids))
    if data.user_id is not None:
        filters.append(Membership.user_id == data.user_id)
    members = (
        db.scalars(
            select(Membership).where(
                Membership.organization_id == data.organization_id, or_(*filters)
            )
        ).all()
        if filters
        else []
    )
    return MemberReferencesResult(
        organization_id=data.organization_id,
        members=[
            MemberReference(membership_id=member.id, user_id=member.user_id, status=member.status)
            for member in members
        ],
    )
