import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import Depends, Header, Request
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ApiError
from app.features.identity.introspection import IntrospectionResult, MembershipResult, signature
from app.features.identity.models import Membership, Organization, User, UserSession
from app.features.identity.routes import require_membership as require_local_membership
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


def authorize_membership_remote(token: str, organization_id: uuid.UUID) -> MembershipResult:
    timestamp = str(int(time.time()))
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.post(
                f"{settings.identity_internal_url.rstrip('/')}/internal/v1/membership/authorize",
                json={"session_token": token, "organization_id": str(organization_id)},
                headers={
                    "X-Internal-Timestamp": timestamp,
                    "X-Internal-Signature": signature(
                        timestamp, token, f"membership:{organization_id}"
                    ),
                },
            )
    except httpx.RequestError as exc:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível") from exc
    if response.status_code == 401:
        raise ApiError(401, "unauthorized", "Sessão inválida")
    if response.status_code == 404:
        raise ApiError(404, "not_found", "Organização não encontrada")
    if response.status_code != 200:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível")
    try:
        result = MembershipResult.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível") from exc
    if result.organization_id != organization_id:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível")
    return result


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


def require_business_membership(
    db: DB,
    auth: AuthContext,
    organization_id: uuid.UUID,
    allowed: set[str] | None = None,
    for_update: bool = False,
) -> tuple[Organization, Membership]:
    if settings.business_auth_mode == "database":
        return require_local_membership(db, auth, organization_id, allowed, for_update)
    result = authorize_membership_remote(auth.token, organization_id)
    if result.user_id != auth.user.id:
        raise ApiError(503, "identity_unavailable", "Identidade indisponível")
    if allowed is not None and result.role not in allowed:
        raise ApiError(403, "forbidden", "Permissão insuficiente")
    statement = select(Organization).where(Organization.id == organization_id)
    if for_update:
        statement = statement.with_for_update()
    organization = db.scalar(statement)
    if organization is None or organization.status != "active":
        raise ApiError(404, "not_found", "Organização não encontrada")
    member = Membership(
        id=result.membership_id,
        organization_id=organization_id,
        user_id=result.user_id,
        role=result.role,
        status="active",
    )
    return organization, member


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
