import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.errors import ApiError
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


def signature(timestamp: str, session_token: str, csrf_token: str | None) -> str:
    message = f"{timestamp}\n{session_token}\n{csrf_token or ''}".encode()
    return hmac.new(settings.auth_hash_key.encode(), message, hashlib.sha256).hexdigest()


@router.post("/session/introspect", response_model=IntrospectionResult)
def introspect(
    data: IntrospectionInput,
    db: DB,
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
) -> IntrospectionResult:
    try:
        issued_at = int(x_internal_timestamp)
    except ValueError as exc:
        raise ApiError(403, "forbidden", "Serviço não autorizado") from exc
    valid_signature = len(x_internal_signature) == 64 and hmac.compare_digest(
        x_internal_signature, signature(x_internal_timestamp, data.session_token, data.csrf_token)
    )
    if abs(time.time() - issued_at) > 30 or not valid_signature:
        raise ApiError(403, "forbidden", "Serviço não autorizado")
    auth = authenticate_token(db, data.session_token)
    csrf_valid = data.csrf_token is not None and hmac.compare_digest(
        digest(data.csrf_token), auth.session.csrf_hash
    )
    return IntrospectionResult(
        user_id=auth.user.id, session_id=auth.session.id, csrf_valid=csrf_valid
    )
