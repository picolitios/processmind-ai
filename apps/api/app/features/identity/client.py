import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import Depends, Header, Request
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import ApiError
from app.features.identity.introspection import IntrospectionResult, signature
from app.features.identity.models import User, UserSession
from app.features.identity.security import (
    DB,
    AuthContext,
    cookie_scheme,
    get_current_auth,
    require_csrf,
    validate_origin,
)


def introspect_remote(token: str, csrf_token: str | None = None) -> IntrospectionResult:
    timestamp = str(int(time.time()))
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.post(
                f"{settings.identity_internal_url.rstrip('/')}/internal/v1/session/introspect",
                json={"session_token": token, "csrf_token": csrf_token},
                headers={
                    "X-Internal-Timestamp": timestamp,
                    "X-Internal-Signature": signature(timestamp, token, csrf_token),
                },
            )
    except httpx.RequestError as exc:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível") from exc
    if response.status_code == 401:
        raise ApiError(401, "unauthorized", "Sessão inválida")
    if response.status_code != 200:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível")
    try:
        return IntrospectionResult.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível") from exc


def get_business_auth(db: DB, token: Annotated[str | None, Depends(cookie_scheme)]) -> AuthContext:
    if settings.business_auth_mode == "database":
        return get_current_auth(db, token)
    if not token:
        raise ApiError(401, "unauthorized", "Sessão necessária")
    principal = introspect_remote(token)
    user = User(id=principal.user_id, email="", password_hash="", status="active")
    session = UserSession(
        id=principal.session_id,
        user_id=principal.user_id,
        token_hash="",
        csrf_hash="",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    return AuthContext(user=user, session=session, token=token)


BusinessAuth = Annotated[AuthContext, Depends(get_business_auth)]


def require_business_csrf(
    request: Request,
    auth: BusinessAuth,
    supplied: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    if settings.business_auth_mode == "database":
        return require_csrf(request, auth, supplied)
    if not supplied:
        raise ApiError(403, "csrf_failed", "Token CSRF inválido")
    validate_origin(request)
    principal = introspect_remote(auth.token, supplied)
    if (
        not principal.csrf_valid
        or principal.user_id != auth.user.id
        or principal.session_id != auth.session.id
    ):
        raise ApiError(403, "csrf_failed", "Token CSRF inválido")
    return auth


BusinessCsrfAuth = Annotated[AuthContext, Depends(require_business_csrf)]
