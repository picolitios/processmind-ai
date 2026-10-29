"""Recuperação limitada de documentação ativa e seleção de ferramentas."""

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.enterprise_agent.models import AgentConfiguration, KnowledgeSource

MAX_SOURCES = 5
MAX_EXCERPT = 3000
QUESTION_STOPWORDS = {
    "como",
    "funciona",
    "funcionar",
    "qual",
    "quais",
    "sobre",
    "esse",
    "essa",
    "para",
    "empresa",
    "processo",
}


def purchasing_requested(question: str) -> bool:
    """Route explicit purchase-analysis requests to the existing audit evidence tool."""
    text = question.casefold()
    purchase = re.search(r"compr|pedido|fornecedor|transa[cç][aã]o|aquisi[cç][aã]o", text)
    analysis = re.search(r"an[aá]lis|alerta|anomalia|duplicad|atras|diverg|auditor", text)
    return bool(purchase and analysis)


def documentation_requested(question: str) -> bool:
    """Keep process questions on the knowledge tool even when search has no match."""
    return bool(
        re.search(
            r"process|procediment|document|manual|pol[ií]tic|aprova[cç][aã]o|como funciona",
            question.casefold(),
        )
    )


def agent_flags(db: Session, organization_id: uuid.UUID) -> tuple[bool, bool]:
    config = db.get(AgentConfiguration, organization_id)
    return (config.agent_enabled, config.purchasing_enabled) if config else (False, True)


def knowledge_context(
    db: Session,
    organization_id: uuid.UUID,
    question: str,
) -> tuple[dict[str, Any], set[uuid.UUID], bool]:
    """Search only enabled tenant documents; bound titles and excerpts sent to Ollama."""
    document = func.to_tsvector(
        "portuguese",
        func.coalesce(KnowledgeSource.title, "") + " " + func.coalesce(KnowledgeSource.content, ""),
    )
    terms = [
        word
        for word in re.findall(r"[\wÀ-ÿ]+", question.casefold()[:300])
        if len(word) > 3 and word not in QUESTION_STOPWORDS
    ][:8]
    if not terms:
        return {"knowledge": []}, set(), False
    needle = func.websearch_to_tsquery("portuguese", " OR ".join(terms))
    rows = db.scalars(
        select(KnowledgeSource)
        .where(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.enabled.is_(True),
            document.op("@@")(needle),
        )
        .order_by(
            func.ts_rank(document, needle).desc(),
            KnowledgeSource.updated_at.desc(),
            KnowledgeSource.id,
        )
        .limit(MAX_SOURCES + 1)
    ).all()
    chosen = rows[:MAX_SOURCES]
    return (
        {
            "knowledge": [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "revision": item.revision,
                    "excerpt": item.content[:MAX_EXCERPT],
                }
                for item in chosen
            ],
        },
        {item.id for item in chosen},
        len(rows) > MAX_SOURCES or any(len(item.content) > MAX_EXCERPT for item in chosen),
    )
