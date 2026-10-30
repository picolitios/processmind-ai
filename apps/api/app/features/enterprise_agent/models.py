"""Dados empresariais do agente e do primeiro conector gerenciado."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentConfiguration(Base):
    """Flags por organização; ausência da linha mantém o novo agente desligado."""

    __tablename__ = "agent_configurations"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    agent_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purchasing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class KnowledgeSource(Base):
    """Documento autorizado, gerenciado ou copiado de um repositório público."""

    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="managed_knowledge", server_default="managed_knowledge"
    )
    github_owner: Mapped[str | None] = mapped_column(String(39))
    github_repo: Mapped[str | None] = mapped_column(String(100))
    github_path: Mapped[str | None] = mapped_column(String(240))
    github_blob_sha: Mapped[str | None] = mapped_column(String(40))
    github_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_knowledge_source_org_id"),
        Index("ix_knowledge_source_org_enabled", "organization_id", "enabled", "created_at", "id"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 160", name="ck_knowledge_title"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="ck_knowledge_content"),
        CheckConstraint("revision > 0", name="ck_knowledge_revision"),
        CheckConstraint(
            "(source_type = 'managed_knowledge' AND github_owner IS NULL "
            "AND github_repo IS NULL AND github_path IS NULL AND github_blob_sha IS NULL "
            "AND github_checked_at IS NULL) "
            "OR (source_type = 'github_public' AND github_owner IS NOT NULL "
            "AND github_repo IS NOT NULL AND github_path IS NOT NULL "
            "AND github_blob_sha IS NOT NULL AND github_checked_at IS NOT NULL)",
            name="ck_knowledge_origin",
        ),
        Index(
            "uq_knowledge_github_path", "organization_id", "github_owner", "github_repo",
            "github_path", unique=True,
        ),
    )
