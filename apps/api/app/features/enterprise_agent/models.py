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
    """Documento textual gerenciado, com autorização e revogação por tenant."""

    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
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
    )
