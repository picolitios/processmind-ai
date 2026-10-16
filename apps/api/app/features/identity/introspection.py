import hashlib
import hmac
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.errors import ApiError
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


def signature(timestamp: str, session_token: str, csrf_token: str | None) -> str:
    message = f"{timestamp}\n{session_token}\n{csrf_token or ''}".encode()
    return hmac.new(settings.auth_hash_key.encode(), message, hashlib.sha256).hexdigest()


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
