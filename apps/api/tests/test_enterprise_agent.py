"""Acceptance checks for authorized documents and agent capability gates."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.db.engine import make_engine
from app.features.copilot.schemas import KnowledgeResult
from app.features.copilot.worker import process_copilot_job
from app.features.ingestion.models import Job
from app.main import app


def test_document_result_rejects_invented_citations_and_links() -> None:
    known = uuid.uuid4()
    valid = KnowledgeResult(answer="O procedimento está documentado.", knowledge_ids=[known])
    valid.validate_sources({known})
    with pytest.raises(ValueError):
        valid.validate_sources({uuid.uuid4()})
    with pytest.raises(ValueError):
        KnowledgeResult(answer="Veja https://example.com", knowledge_ids=[known]).validate_sources(
            {known}
        )


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required")
def test_agent_document_flow_and_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.copilot import worker

    with TestClient(app) as owner, TestClient(app) as outsider:
        csrf = login(owner, create_user(owner, "enterprise-agent-owner"))
        outsider_csrf = login(outsider, create_user(outsider, "enterprise-agent-outsider"))
        org = create_org(owner, csrf, "enterprise-agent-org")
        base = f"/api/v1/organizations/{org}"
        assert owner.get(f"{base}/agent/configuration").json() == {
            "agent_enabled": False,
            "purchasing_enabled": True,
        }
        assert (
            owner.post(
                f"{base}/ai/copilot/conversations",
                headers=csrf_headers(csrf),
                json={"scope": "organization", "mode": "normal"},
            ).status_code
            == 403
        )
        assert (
            owner.put(
                f"{base}/agent/configuration",
                json={
                    "agent_enabled": True,
                    "purchasing_enabled": False,
                },
            ).status_code
            == 403
        )
        assert (
            owner.put(
                f"{base}/agent/configuration",
                headers=csrf_headers(csrf),
                json={"agent_enabled": True, "purchasing_enabled": False},
            ).status_code
            == 200
        )
        created = owner.post(
            f"{base}/integrations/knowledge",
            headers=csrf_headers(csrf),
            json={
                "title": "Aprovação de compras",
                "content": (
                    "O processo de aprovação de compras exige validação "
                    "do líder antes do pedido."
                ),
                "enabled": True,
            },
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        assert outsider.get(f"{base}/integrations/knowledge/{source_id}").status_code == 404
        assert (
            outsider.patch(
                f"{base}/integrations/knowledge/{source_id}",
                headers=csrf_headers(outsider_csrf),
                json={"enabled": False},
            ).status_code
            == 404
        )
        assert owner.get(f"{base}/agent/capabilities").json()["knowledge_available"] is True
        chat = owner.post(
            f"{base}/ai/copilot/conversations",
            headers=csrf_headers(csrf),
            json={"scope": "organization", "mode": "normal"},
        )
        assert chat.status_code == 201, chat.text
        conversation_id = chat.json()["id"]
        asked = owner.post(
            f"{base}/ai/copilot/conversations/{conversation_id}/questions",
            headers={**csrf_headers(csrf), "Idempotency-Key": uuid.uuid4().hex},
            json={"question": "Como funciona a aprovação de compras?"},
        )
        assert asked.status_code == 202, asked.text

        def answer(context: dict[str, object], model: str, schema: object, system: str):
            assert "allowed_knowledge_ids" in context
            assert source_id in context["allowed_knowledge_ids"]
            assert "dados não confiáveis" in system
            return KnowledgeResult(
                answer="A documentação exige validação do líder.",
                knowledge_ids=[uuid.UUID(source_id)],
            ), model

        monkeypatch.setattr(worker, "call_structured", answer)
        with Session(make_engine()) as db:
            job = db.get(Job, uuid.UUID(asked.json()["job_id"]))
            assert job is not None
            job.status = "running"
            db.commit()
            process_copilot_job(db, job.id)
        question_id = asked.json()["question_id"]
        result = owner.get(f"{base}/ai/copilot/questions/{question_id}")
        assert result.status_code == 200
        assert result.json()["status"] == "succeeded"
        assert result.json()["knowledge_citations"][0]["source_id"] == source_id
        assert result.json()["citations"] == []
        disabled = owner.patch(
            f"{base}/integrations/knowledge/{source_id}",
            headers=csrf_headers(csrf),
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        revoked_answer = owner.get(f"{base}/ai/copilot/questions/{question_id}").json()
        assert revoked_answer["knowledge_citations"] == []
        assert "desatualizada" in revoked_answer["limitation"]
        assert owner.get(f"{base}/agent/capabilities").json()["knowledge_available"] is False
        for text, expected_error in (
            ("Como funciona a aprovação de compras?", "insufficient_evidence"),
            ("Analise os alertas de compras", "tool_disabled"),
        ):
            queued = owner.post(
                f"{base}/ai/copilot/conversations/{conversation_id}/questions",
                headers={**csrf_headers(csrf), "Idempotency-Key": uuid.uuid4().hex},
                json={"question": text},
            )
            assert queued.status_code == 202
            with Session(make_engine()) as db:
                job = db.get(Job, uuid.UUID(queued.json()["job_id"]))
                assert job is not None
                job.status = "running"
                db.commit()
                process_copilot_job(db, job.id)
            failed = owner.get(f"{base}/ai/copilot/questions/{queued.json()['question_id']}")
            assert failed.json()["status"] == "failed"
            with Session(make_engine()) as db:
                job = db.get(Job, uuid.UUID(queued.json()["job_id"]))
                assert job is not None and job.error_code == expected_error
