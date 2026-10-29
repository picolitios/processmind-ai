"""Administração das capacidades e da documentação autorizada do agente."""

import uuid
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import and_, or_, select

from app.core.errors import ApiError
from app.features.audit.routes import make_cursor
from app.features.audit_trail.events import append_business_event
from app.features.enterprise_agent.models import AgentConfiguration, KnowledgeSource
from app.features.enterprise_agent.schemas import ConfigurationInput, KnowledgeInput, KnowledgePatch
from app.features.identity.client import BusinessAuth as Auth
from app.features.identity.client import BusinessCsrfAuth as CsrfAuth
from app.features.identity.client import require_business_membership as require_membership
from app.features.identity.routes import parse_cursor
from app.features.identity.security import DB

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["enterprise-agent"])
MANAGERS = {"owner", "admin"}


def configuration_view(config: AgentConfiguration | None) -> dict[str, bool]:
    return {
        "agent_enabled": config.agent_enabled if config else False,
        "purchasing_enabled": config.purchasing_enabled if config else True,
    }


def source_view(source: KnowledgeSource, *, include_content: bool = False) -> dict[str, Any]:
    result = {
        "id": source.id,
        "title": source.title,
        "type": "managed_knowledge",
        "enabled": source.enabled,
        "revision": source.revision,
        "created_by_user_id": source.created_by_user_id,
        "updated_by_user_id": source.updated_by_user_id,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }
    if include_content:
        result["content"] = source.content
    return result


def find_source(
    db: DB, organization_id: uuid.UUID, source_id: uuid.UUID, *, lock: bool = False
) -> KnowledgeSource:
    query = select(KnowledgeSource).where(
        KnowledgeSource.organization_id == organization_id,
        KnowledgeSource.id == source_id,
    )
    source = db.scalar(query.with_for_update() if lock else query)
    if source is None:
        raise ApiError(404, "not_found", "Fonte não encontrada")
    return source


@router.get("/agent/configuration")
def get_configuration(organization_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, bool]:
    require_membership(db, auth, organization_id)
    return configuration_view(db.get(AgentConfiguration, organization_id))


@router.put("/agent/configuration")
def put_configuration(
    organization_id: uuid.UUID,
    data: ConfigurationInput,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, bool]:
    require_membership(db, auth, organization_id, MANAGERS)
    config = db.get(AgentConfiguration, organization_id)
    if config is None:
        config = AgentConfiguration(organization_id=organization_id)
        db.add(config)
    config.agent_enabled = data.agent_enabled
    config.purchasing_enabled = data.purchasing_enabled
    config.updated_by_user_id = auth.user.id
    append_business_event(
        db,
        organization_id,
        auth.user.id,
        "agent.configuration_updated",
        "agent_configuration",
        organization_id,
    )
    db.commit()
    return configuration_view(config)


@router.get("/agent/capabilities")
def get_capabilities(organization_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    _, membership = require_membership(db, auth, organization_id)
    config = configuration_view(db.get(AgentConfiguration, organization_id))
    document_count = db.scalars(
        select(KnowledgeSource.id)
        .where(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.enabled.is_(True),
        )
        .limit(1)
    ).first()
    return {
        **config,
        "can_chat": config["agent_enabled"] and membership.role in {"owner", "admin", "analyst"},
        "knowledge_available": document_count is not None,
        "tools": [
            {"id": "managed_knowledge", "enabled": document_count is not None},
            {"id": "purchasing_audit", "enabled": config["purchasing_enabled"]},
        ],
    }


@router.get("/integrations/knowledge")
def list_sources(
    organization_id: uuid.UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> dict[str, Any]:
    _, member = require_membership(db, auth, organization_id)
    query = select(KnowledgeSource).where(KnowledgeSource.organization_id == organization_id)
    if member.role not in MANAGERS:
        query = query.where(KnowledgeSource.enabled.is_(True))
    if cursor:
        when, item_id = parse_cursor(cursor)
        query = query.where(
            or_(
                KnowledgeSource.created_at < when,
                and_(KnowledgeSource.created_at == when, KnowledgeSource.id < item_id),
            )
        )
    rows = db.scalars(
        query.order_by(KnowledgeSource.created_at.desc(), KnowledgeSource.id.desc()).limit(
            limit + 1
        )
    ).all()
    page = rows[:limit]
    return {
        "items": [source_view(item) for item in page],
        "next_cursor": make_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None,
    }


@router.post("/integrations/knowledge", status_code=201)
def create_source(
    organization_id: uuid.UUID,
    data: KnowledgeInput,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, MANAGERS)
    source = KnowledgeSource(
        organization_id=organization_id,
        title=data.title,
        content=data.content,
        enabled=data.enabled,
        created_by_user_id=auth.user.id,
        updated_by_user_id=auth.user.id,
    )
    db.add(source)
    db.flush()
    append_business_event(
        db, organization_id, auth.user.id, "knowledge.created", "knowledge_source", source.id
    )
    db.commit()
    return source_view(source, include_content=True)


@router.get("/integrations/knowledge/{source_id}")
def get_source(
    organization_id: uuid.UUID, source_id: uuid.UUID, db: DB, auth: Auth
) -> dict[str, Any]:
    _, member = require_membership(db, auth, organization_id)
    source = find_source(db, organization_id, source_id)
    if not source.enabled and member.role not in MANAGERS:
        raise ApiError(404, "not_found", "Fonte não encontrada")
    return source_view(source, include_content=True)


@router.patch("/integrations/knowledge/{source_id}")
def patch_source(
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    data: KnowledgePatch,
    db: DB,
    auth: CsrfAuth,
) -> dict[str, Any]:
    require_membership(db, auth, organization_id, MANAGERS)
    if not data.model_fields_set:
        raise ApiError(422, "empty_update", "Informe ao menos uma alteração")
    source = find_source(db, organization_id, source_id, lock=True)
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None:
            raise ApiError(422, "null_not_allowed", "Campo não pode ser nulo")
        setattr(source, field, value)
    source.revision += 1
    source.updated_by_user_id = auth.user.id
    append_business_event(
        db,
        organization_id,
        auth.user.id,
        "knowledge.updated",
        "knowledge_source",
        source.id,
        {"enabled": source.enabled, "revision": source.revision},
    )
    db.commit()
    return source_view(source, include_content=True)
