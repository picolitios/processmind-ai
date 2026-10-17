import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.db.engine import make_engine
from app.features.audit.models import AuditFinding, AuditRun, FindingEvidence
from app.features.copilot.models import CopilotConversation, CopilotTurn
from app.features.copilot.schemas import CopilotResult
from app.features.copilot.worker import (
    build_copilot_context,
    process_copilot_job,
    purge_expired_temporary,
)
from app.features.ingestion.models import ImportBatch, ImportRow, Job
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def seed_targets(organization_id: str, user_id: str) -> tuple[str, list[str], list[str]]:
    """Create two findings with different evidence under one completed audit."""
    tenant = uuid.UUID(organization_id)
    with Session(make_engine()) as db:
        batch = ImportBatch(
            organization_id=tenant, uploader_id=uuid.UUID(user_id),
            sha256=uuid.uuid4().hex, original_name="copilot.csv",
            private_storage_key=uuid.uuid4().hex, file_format="csv",
            status="succeeded", mapping={"columns": {}},
        )
        db.add(batch)
        db.flush()
        run = AuditRun(
            organization_id=tenant, requester_id=uuid.UUID(user_id),
            status="succeeded", rule_set_version="1.0.0", config_snapshot={},
            import_ids=[], idempotency_key=uuid.uuid4().hex,
        )
        db.add(run)
        db.flush()
        finding_ids: list[str] = []
        evidence_ids: list[str] = []
        for number in (1, 2):
            row = ImportRow(
                organization_id=tenant, batch_id=batch.id, row_number=number,
                raw_json={}, normalized_json={}, errors=[],
            )
            db.add(row)
            db.flush()
            finding = AuditFinding(
                organization_id=tenant, run_id=run.id, rule_code="DUPLICATE",
                rule_version="1.0.0", severity="medium", review_state="unreviewed",
                explanation="Compra duplicada", fingerprint=uuid.uuid4().hex,
            )
            db.add(finding)
            db.flush()
            evidence = FindingEvidence(
                organization_id=tenant, finding_id=finding.id,
                import_row_id=row.id, evidence_json={"note": f"Evidência {number}"},
            )
            db.add(evidence)
            db.flush()
            finding_ids.append(str(finding.id))
            evidence_ids.append(str(evidence.id))
        run_id = str(run.id)
        db.commit()
    return run_id, finding_ids, evidence_ids


def create_chat(
    client: TestClient, base: str, csrf: str, finding_id: str, mode: str,
) -> dict[str, str]:
    response = client.post(
        f"{base}/copilot/conversations", headers=csrf_headers(csrf),
        json={"finding_id": finding_id, "mode": mode},
    )
    assert response.status_code == 201, response.text
    return response.json()


def ask(
    client: TestClient, base: str, csrf: str, conversation_id: str, question: str,
) -> dict[str, str]:
    response = client.post(
        f"{base}/copilot/conversations/{conversation_id}/questions",
        headers={**csrf_headers(csrf), "Idempotency-Key": uuid.uuid4().hex},
        json={"question": question},
    )
    assert response.status_code == 202, response.text
    return response.json()


def finish_question(
    monkeypatch: pytest.MonkeyPatch, question: dict[str, str], evidence_id: str,
) -> None:
    """Run the real worker boundary with a deterministic structured model response."""
    from app.features.copilot import worker

    def answer(context: dict[str, object], model: str, schema: object, system: str):
        assert "histórico" in system
        result = CopilotResult(answer="Verifique o documento citado.", evidence_ids=[evidence_id])
        return result, model

    monkeypatch.setattr(worker, "call_structured", answer)
    with Session(make_engine()) as db:
        job = db.get(Job, uuid.UUID(question["job_id"]))
        assert job is not None
        job.status = "running"
        db.commit()
        process_copilot_job(db, job.id)


def test_copilot_memory_is_tenant_scoped_and_temporary_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as owner, TestClient(app) as outsider:
        csrf = login(owner, create_user(owner, "copilot-owner"))
        org_id = create_org(owner, csrf, "copilot-org")
        user_id = owner.get("/api/v1/auth/session").json()["user"]["id"]
        _, findings, evidence = seed_targets(org_id, user_id)
        base = f"/api/v1/organizations/{org_id}/ai"
        first = create_chat(owner, base, csrf, findings[0], "normal")
        first_question = ask(owner, base, csrf, first["id"], "O que verificar?")
        finish_question(monkeypatch, first_question, evidence[0])
        answer = owner.get(f"{base}/copilot/questions/{first_question['question_id']}")
        assert answer.status_code == 200
        assert answer.json()["citations"][0]["evidence_id"] == evidence[0]

        second = create_chat(owner, base, csrf, findings[1], "normal")
        second_question = ask(owner, base, csrf, second["id"], "Há padrão anterior?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(second["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(second_question["question_id"]))
            assert conversation is not None and turn is not None
            context, allowed, _ = build_copilot_context(db, conversation, turn)
        assert context["organization_memory"][0]["answer"] == "Verifique o documento citado."
        assert uuid.UUID(evidence[0]) in allowed
        finish_question(monkeypatch, second_question, evidence[1])

        temporary = create_chat(owner, base, csrf, findings[1], "temporary")
        temp_question = ask(owner, base, csrf, temporary["id"], "Sem memória externa?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(temporary["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(temp_question["question_id"]))
            assert conversation is not None and turn is not None
            context, allowed, _ = build_copilot_context(db, conversation, turn)
        assert context["organization_memory"] == []
        assert uuid.UUID(evidence[0]) not in allowed
        finish_question(monkeypatch, temp_question, evidence[1])
        next_temp_question = ask(owner, base, csrf, temporary["id"], "E agora?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(temporary["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(next_temp_question["question_id"]))
            assert conversation is not None and turn is not None
            context, _, _ = build_copilot_context(db, conversation, turn)
        assert context["history"][0]["question"] == "Sem memória externa?"
        assert context["organization_memory"] == []
        finish_question(monkeypatch, next_temp_question, evidence[1])
        listed = owner.get(f"{base}/copilot/conversations", params={"finding_id": findings[1]})
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [second["id"]]

        invalid = create_chat(owner, base, csrf, findings[0], "normal")
        invalid_question = ask(owner, base, csrf, invalid["id"], "Posso citar outro ID?")
        finish_question(monkeypatch, invalid_question, str(uuid.uuid4()))
        invalid_answer = owner.get(f"{base}/copilot/questions/{invalid_question['question_id']}")
        assert invalid_answer.json()["status"] == "failed"
        assert invalid_answer.json()["citations"] == []

        other_csrf = login(outsider, create_user(outsider, "copilot-outsider"))
        create_org(outsider, other_csrf, "copilot-other")
        outsider_question = outsider.get(
            f"{base}/copilot/questions/{first_question['question_id']}"
        )
        assert outsider_question.status_code == 404
        assert outsider.get(f"{base}/copilot/conversations/{first['id']}").status_code == 404


def test_policy_approval_idempotency_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as owner, TestClient(app) as analyst:
        owner_csrf = login(owner, create_user(owner, "copilot-manager"))
        analyst_email = create_user(analyst, "copilot-analyst")
        analyst_csrf = login(analyst, analyst_email)
        org_id = create_org(owner, owner_csrf, "copilot-policy")
        user_id = owner.get("/api/v1/auth/session").json()["user"]["id"]
        _, findings, evidence = seed_targets(org_id, user_id)
        base = f"/api/v1/organizations/{org_id}/ai"
        added = owner.post(
            f"/api/v1/organizations/{org_id}/users",
            headers=csrf_headers(owner_csrf),
            json={"email": analyst_email, "role": "analyst"},
        )
        assert added.status_code == 201, added.text
        policy = owner.put(
            f"{base}/copilot/policy", headers=csrf_headers(owner_csrf),
            json={"temporary_default": True, "memory_turn_limit": 0},
        )
        assert policy.status_code == 200
        assert analyst.get(f"{base}/copilot/policy").json()["temporary_default"] is True
        assert analyst.put(
            f"{base}/copilot/policy", headers=csrf_headers(analyst_csrf),
            json={"temporary_default": False, "memory_turn_limit": 10},
        ).status_code == 403
        pending = create_chat(analyst, base, analyst_csrf, findings[0], "normal")
        assert pending["status"] == "pending"
        assert analyst.post(
            f"{base}/copilot/conversations/{pending['id']}/questions",
            headers={**csrf_headers(analyst_csrf), "Idempotency-Key": uuid.uuid4().hex},
            json={"question": "Pode responder?"},
        ).status_code == 409
        assert owner.get(f"{base}/copilot/approvals").json()["items"][0]["id"] == pending["id"]
        assert owner.post(
            f"{base}/copilot/conversations/{pending['id']}/approve",
            headers=csrf_headers(owner_csrf),
        ).status_code == 200
        key = uuid.uuid4().hex
        path = f"{base}/copilot/conversations/{pending['id']}/questions"
        headers = {**csrf_headers(analyst_csrf), "Idempotency-Key": key}
        first = analyst.post(path, headers=headers, json={"question": "Agora?"})
        assert first.status_code == 202
        repeated = analyst.post(path, headers=headers, json={"question": "Agora?"})
        assert repeated.json() == first.json()
        assert analyst.post(path, headers=headers, json={"question": "Outra?"}).status_code == 409
        assert analyst.post(
            f"{base}/copilot/conversations/{pending['id']}/reject",
            headers=csrf_headers(analyst_csrf),
        ).status_code == 403
        finish_question(monkeypatch, first.json(), evidence[0])

        temporary = create_chat(analyst, base, analyst_csrf, findings[0], "temporary")
        with Session(make_engine()) as db:
            chat = db.get(CopilotConversation, uuid.UUID(temporary["id"]))
            assert chat is not None
            chat.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()
            assert purge_expired_temporary(db) == 1
        assert analyst.get(f"{base}/copilot/conversations/{temporary['id']}").status_code == 404
