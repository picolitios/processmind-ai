import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, Header, Request
from fastapi.security import APIKeyCookie
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.features.identity.models import LoginFailure, User, UserSession

DB = Annotated[Session, Depends(get_db)]
cookie_scheme = APIKeyCookie(name="pm_session", auto_error=False)
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash("not-a-valid-account-password")
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LIMIT = 5


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def email_digest(email: str) -> str:
    return hmac.new(
        settings.auth_hash_key.encode("utf-8"), email.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def csrf_for_token(token: str) -> str:
    return digest(f"csrf:{token}")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bool(password_hasher.verify(stored_hash, password))
    except VerificationError:
        return False


def check_login_limit(db: Session, email: str) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": email_digest(email)},
    )
    cutoff = datetime.now(UTC) - LOGIN_WINDOW
    count = db.scalar(
        select(func.count())
        .select_from(LoginFailure)
        .where(LoginFailure.email_hash == email_digest(email), LoginFailure.occurred_at >= cutoff)
    )
    if count is not None and count >= LOGIN_LIMIT:
        raise ApiError(429, "login_rate_limited", "Tente novamente mais tarde")


def record_login_failure(db: Session, email: str, request: Request) -> None:
    address = request.client.host if request.client else "unknown"
    db.execute(
        delete(LoginFailure).where(LoginFailure.occurred_at < datetime.now(UTC) - timedelta(days=1))
    )
    db.add(LoginFailure(email_hash=email_digest(email), ip_hash=email_digest(address)))
    db.commit()


def clear_login_failures(db: Session, email: str) -> None:
    db.execute(delete(LoginFailure).where(LoginFailure.email_hash == email_digest(email)))


def issue_session(db: Session, user: User) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        token_hash=digest(token),
        csrf_hash=digest(csrf_for_token(token)),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_hours),
    )
    db.add(session)
    db.flush()
    return token, session


def rotate_existing_session(db: Session, request: Request) -> None:
    token = request.cookies.get("pm_session")
    if token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == digest(token)))
        if session is not None:
            session.revoked_at = datetime.now(UTC)


def validate_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if origin is not None and origin != settings.web_origin:
        raise ApiError(403, "origin_forbidden", "Origem não permitida")


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession
    token: str


def get_current_auth(db: DB, token: Annotated[str | None, Depends(cookie_scheme)]) -> AuthContext:
    if not token:
        raise ApiError(401, "unauthorized", "Sessão necessária")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == digest(token)))
    if session is None or session.revoked_at or session.expires_at <= datetime.now(UTC):
        raise ApiError(401, "unauthorized", "Sessão inválida")
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise ApiError(401, "unauthorized", "Sessão inválida")
    return AuthContext(user=user, session=session, token=token)


Auth = Annotated[AuthContext, Depends(get_current_auth)]


def require_csrf(
    request: Request,
    auth: Auth,
    supplied: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    if not supplied or not hmac.compare_digest(digest(supplied), auth.session.csrf_hash):
        raise ApiError(403, "csrf_failed", "Token CSRF inválido")
    validate_origin(request)
    return auth


CsrfAuth = Annotated[AuthContext, Depends(require_csrf)]


def revoke_user_sessions(db: Session, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    for session in db.scalars(
        select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    ):
        session.revoked_at = now
