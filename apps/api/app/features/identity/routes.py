import base64
import binascii
import json
import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.errors import ApiError
from app.features.audit.models import AuditConfiguration
from app.features.identity.config_sync import complete_pending, pending_for_organizations
from app.features.identity.models import (
    AuditEvent,
    Membership,
    Organization,
    OrganizationConfigCommand,
    User,
)
from app.features.identity.schemas import (
    LoginInput,
    MemberInput,
    MemberPage,
    MemberPatch,
    MemberStatus,
    MemberView,
    OrganizationInput,
    OrganizationSettingsInput,
    OrganizationView,
    RegisterInput,
    Role,
    SessionView,
    UserView,
)
from app.features.identity.security import (
    DB,
    Auth,
    AuthContext,
    CsrfAuth,
    check_login_limit,
    clear_login_failures,
    csrf_for_token,
    dummy_password_hash,
    issue_session,
    password_hasher,
    record_login_failure,
    revoke_user_sessions,
    rotate_existing_session,
    validate_origin,
    verify_password,
)

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
organizations_router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


def user_view(user: User) -> UserView:
    return UserView(id=user.id, email=user.email)


def member_view(member: Membership) -> MemberView:
    return MemberView(
        organization_id=member.organization_id,
        user_id=member.user_id,
        role=cast(Role, member.role),
        status=cast(MemberStatus, member.status),
        created_at=member.created_at,
    )


def organization_view(org: Organization) -> OrganizationView:
    return OrganizationView(
        id=org.id,
        name=org.name,
        slug=org.slug,
        settings_version=org.settings_version,
        settings=org.settings,
    )


def session_view(db: DB, auth: Auth) -> SessionView:
    members = db.scalars(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == auth.user.id,
            Membership.status == "active",
            Organization.status == "active",
        )
    ).all()
    return SessionView(
        user=user_view(auth.user),
        memberships=[member_view(member) for member in members],
        csrf_token=csrf_for_token(auth.token),
    )


def log_event(
    db: DB,
    request: Request,
    action: str,
    actor_user_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    organization_id: uuid.UUID | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            metadata_json={},
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )


def require_membership(
    db: DB,
    auth: Auth,
    organization_id: uuid.UUID,
    allowed: set[str] | None = None,
    for_update: bool = False,
) -> tuple[Organization, Membership]:
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == auth.user.id,
            Membership.status == "active",
        )
    )
    if for_update and membership is not None:
        organization = db.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        db.refresh(membership)
    else:
        organization = db.get(Organization, organization_id) if membership else None
    if (
        organization is None
        or membership is None
        or organization.status != "active"
        or membership.status != "active"
    ):
        raise ApiError(404, "not_found", "Organização não encontrada")
    if allowed is not None and membership.role not in allowed:
        raise ApiError(403, "forbidden", "Permissão insuficiente")
    return organization, membership


@auth_router.post("/register", response_model=UserView, status_code=201)
def register(data: RegisterInput, request: Request, db: DB) -> UserView:
    validate_origin(request)
    user = User(email=str(data.email).casefold(), password_hash=password_hasher.hash(data.password))
    db.add(user)
    try:
        db.flush()
        log_event(db, request, "user.registered", user.id, "user", user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "email_conflict", "Email já cadastrado") from exc
    return user_view(user)


@auth_router.post("/login", response_model=SessionView)
def login(data: LoginInput, request: Request, response: Response, db: DB) -> SessionView:
    validate_origin(request)
    email = str(data.email).casefold()
    check_login_limit(db, email)
    user = db.scalar(select(User).where(User.email == email, User.status == "active"))
    stored_hash = user.password_hash if user is not None else dummy_password_hash
    if not verify_password(data.password, stored_hash) or user is None:
        record_login_failure(db, email, request)
        raise ApiError(401, "invalid_credentials", "Credenciais inválidas")
    clear_login_failures(db, email)
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(data.password)
    rotate_existing_session(db, request)
    token, session = issue_session(db, user)
    log_event(db, request, "session.created", user.id, "session", session.id)
    db.commit()
    response.set_cookie(
        "pm_session",
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return session_view(db, AuthContext(user=user, session=session, token=token))


@auth_router.get("/session", response_model=SessionView)
def get_session(db: DB, auth: Auth) -> SessionView:
    return session_view(db, auth)


@auth_router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB, auth: CsrfAuth) -> None:
    auth.session.revoked_at = datetime.now(UTC)
    log_event(db, request, "session.revoked", auth.user.id, "session", auth.session.id)
    db.commit()
    response.delete_cookie("pm_session", path="/", secure=settings.secure_cookies, samesite="lax")


@organizations_router.get("", response_model=list[OrganizationView])
def list_organizations(db: DB, auth: Auth) -> list[OrganizationView]:
    organizations = db.scalars(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == auth.user.id,
            Membership.status == "active",
            Organization.status == "active",
        )
        .order_by(Organization.created_at, Organization.id)
    ).all()
    if settings.audit_config_write_mode == "coordinated" and pending_for_organizations(
        db, [org.id for org in organizations]
    ):
        raise ApiError(503, "audit_configuration_pending", "Configuração indisponível")
    return [organization_view(org) for org in organizations]


@organizations_router.post("", response_model=OrganizationView, status_code=201)
def create_organization(
    data: OrganizationInput, request: Request, db: DB, auth: CsrfAuth
) -> OrganizationView:
    coordinated = settings.audit_config_write_mode == "coordinated"
    org = Organization(
        name=data.name.strip(), slug=data.slug,
        status="provisioning" if coordinated else "active",
    )
    db.add(org)
    try:
        db.flush()
        if coordinated:
            # The durable command survives an audit-owner timeout or process crash.
            db.add(
                OrganizationConfigCommand(
                    organization_id=org.id,
                    settings_version=org.settings_version,
                    kind="provision",
                    amount_limits=org.settings.get("amount_limits", {}),
                    delay_window_days=org.settings.get("delay_window_days", 90),
                )
            )
        else:
            # Database mode preserves the previous shared-transaction rollback path.
            db.add(
                AuditConfiguration(
                    organization_id=org.id,
                    settings_version=org.settings_version,
                    amount_limits=org.settings.get("amount_limits", {}),
                    delay_window_days=org.settings.get("delay_window_days", 90),
                )
            )
        db.add(Membership(organization_id=org.id, user_id=auth.user.id, role="owner"))
        log_event(db, request, "organization.created", auth.user.id, "organization", org.id, org.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if coordinated:
            existing = db.scalar(select(Organization).where(Organization.slug == data.slug))
            if existing is not None and existing.name == data.name.strip():
                owner = db.scalar(
                    select(Membership).where(
                        Membership.organization_id == existing.id,
                        Membership.user_id == auth.user.id,
                        Membership.role == "owner",
                        Membership.status == "active",
                    )
                )
                provision = db.scalar(
                    select(OrganizationConfigCommand).where(
                        OrganizationConfigCommand.organization_id == existing.id,
                        OrganizationConfigCommand.kind == "provision",
                    )
                )
                if owner is not None and provision is not None:
                    # The creator may safely retry after losing the original response.
                    return organization_view(complete_pending(db, existing.id))
        raise ApiError(409, "slug_conflict", "Identificador já utilizado") from exc
    if coordinated:
        org = complete_pending(db, org.id)
    return organization_view(org)


@organizations_router.get("/{organization_id}", response_model=OrganizationView)
def get_organization(organization_id: uuid.UUID, db: DB, auth: Auth) -> OrganizationView:
    org, _ = require_membership(db, auth, organization_id)
    if settings.audit_config_write_mode == "coordinated" and pending_for_organizations(
        db, [organization_id]
    ):
        raise ApiError(503, "audit_configuration_pending", "Configuração indisponível")
    return organization_view(org)


@organizations_router.patch("/{organization_id}", response_model=OrganizationView)
def update_organization(
    organization_id: uuid.UUID,
    data: OrganizationSettingsInput,
    request: Request,
    db: DB,
    auth: CsrfAuth,
) -> OrganizationView:
    org, _ = require_membership(db, auth, organization_id, {"owner", "admin"}, for_update=True)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise ApiError(422, "validation_error", "Nenhuma configuração informada")
    coordinated = settings.audit_config_write_mode == "coordinated"
    if coordinated and pending_for_organizations(db, [organization_id]):
        # Complete the earlier version before accepting another update.
        db.rollback()
        complete_pending(db, organization_id)
        org, _ = require_membership(db, auth, organization_id, {"owner", "admin"}, for_update=True)
    if coordinated and {**org.settings, **changes} == org.settings:
        # Repeating an already confirmed update does not allocate a new version.
        db.rollback()
        return organization_view(org)
    org.settings = {**org.settings, **changes}
    org.settings_version += 1
    if coordinated:
        db.add(
            OrganizationConfigCommand(
                organization_id=org.id,
                settings_version=org.settings_version,
                kind="update",
                amount_limits=org.settings.get("amount_limits", {}),
                delay_window_days=org.settings.get("delay_window_days", 90),
            )
        )
    else:
        # The legacy mode still supports a fully atomic rollback on the shared database.
        audit_config = db.get(AuditConfiguration, org.id, with_for_update=True)
        if audit_config is None:
            raise ApiError(
                503, "audit_configuration_missing", "Configuração de auditoria indisponível"
            )
        audit_config.settings_version = org.settings_version
        audit_config.amount_limits = org.settings.get("amount_limits", {})
        audit_config.delay_window_days = org.settings.get("delay_window_days", 90)
    log_event(
        db, request, "organization.settings_changed", auth.user.id, "organization", org.id, org.id
    )
    db.commit()
    if coordinated:
        org = complete_pending(db, org.id)
    return organization_view(org)


def parse_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor + "==="))
        return datetime.fromisoformat(decoded["created_at"]), uuid.UUID(decoded["id"])
    except (ValueError, TypeError, KeyError, binascii.Error) as exc:
        raise ApiError(422, "invalid_cursor", "Cursor inválido") from exc


def make_cursor(member: Membership) -> str:
    value = json.dumps({"created_at": member.created_at.isoformat(), "id": str(member.id)})
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


@organizations_router.get("/{organization_id}/users", response_model=MemberPage)
def list_members(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> MemberPage:
    require_membership(db, auth, organization_id, {"owner", "admin"})
    statement = select(Membership).where(Membership.organization_id == organization_id)
    if cursor:
        created_at, member_id = parse_cursor(cursor)
        statement = statement.where(
            or_(
                Membership.created_at > created_at,
                and_(Membership.created_at == created_at, Membership.id > member_id),
            )
        )
    members = db.scalars(
        statement.order_by(Membership.created_at, Membership.id).limit(limit + 1)
    ).all()
    page = members[:limit]
    return MemberPage(
        items=[member_view(member) for member in page],
        next_cursor=make_cursor(page[-1]) if len(members) > limit else None,
    )


@organizations_router.post("/{organization_id}/users", response_model=MemberView, status_code=201)
def add_member(
    organization_id: uuid.UUID, data: MemberInput, request: Request, db: DB, auth: CsrfAuth
) -> MemberView:
    require_membership(db, auth, organization_id, {"owner"}, for_update=True)
    user = db.scalar(
        select(User).where(User.email == str(data.email).casefold(), User.status == "active")
    )
    if user is None:
        raise ApiError(404, "not_found", "Usuário não encontrado")
    membership = Membership(organization_id=organization_id, user_id=user.id, role=data.role)
    db.add(membership)
    try:
        db.flush()
        log_event(
            db,
            request,
            "membership.created",
            auth.user.id,
            "membership",
            membership.id,
            organization_id,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "membership_conflict", "Usuário já associado") from exc
    return member_view(membership)


@organizations_router.patch("/{organization_id}/users/{user_id}", response_model=MemberView)
def update_member(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberPatch,
    request: Request,
    db: DB,
    auth: CsrfAuth,
) -> MemberView:
    require_membership(db, auth, organization_id, {"owner"}, for_update=True)
    if data.role is None and data.status is None:
        raise ApiError(422, "validation_error", "Nenhuma alteração informada")
    member = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id, Membership.user_id == user_id
        )
    )
    if member is None:
        raise ApiError(404, "not_found", "Associação não encontrada")
    new_role = data.role or member.role
    new_status = data.status or member.status
    if (
        member.role == "owner"
        and member.status == "active"
        and (new_role != "owner" or new_status != "active")
    ):
        owners = db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == "owner",
                Membership.status == "active",
            )
        )
        if owners is None or owners <= 1:
            raise ApiError(409, "last_owner", "A organização precisa de um Owner ativo")
    if new_role != member.role or new_status != member.status:
        member.role = new_role
        member.status = new_status
        revoke_user_sessions(db, member.user_id)
        log_event(
            db,
            request,
            "membership.changed",
            auth.user.id,
            "membership",
            member.id,
            organization_id,
        )
        db.commit()
    return member_view(member)
