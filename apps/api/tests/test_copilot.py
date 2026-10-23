import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.db.engine import make_engine
from app.features.audit.models import AuditFinding, AuditRun, FindingEvidence
from app.features.copilot.instructions import system_message_for_organization
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


def test_company_instructions_reach_copilot_without_replacing_evidence_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.copilot import worker

    with TestClient(app) as owner:
        csrf = login(owner, create_user(owner, "copilot-instructions"))
        org_id = create_org(owner, csrf, "copilot-instructions")
        user_id = owner.get("/api/v1/auth/session").json()["user"]["id"]
        _, findings, evidence = seed_targets(org_id, user_id)
        base = f"/api/v1/organizations/{org_id}/ai/copilot"
        saved = owner.put(
            f"{base}/policy", headers=csrf_headers(csrf),
            json={"temporary_default": False, "memory_turn_limit": 10,
                  "instructions": "Seja objetivo ao orientar a equipe."},
        )
        assert saved.status_code == 200
        chat = create_chat(owner, f"/api/v1/organizations/{org_id}/ai", csrf,
                           findings[0], "normal")
        question = ask(owner, f"/api/v1/organizations/{org_id}/ai", csrf,
                       chat["id"], "O que conferir?")

        def answer(context: dict[str, object], model: str, schema: object, system: str):
            assert "Seja objetivo ao orientar a equipe." in system
            assert "Cite IDs de evidência existentes" in system
            result = CopilotResult(answer="Confira a compra citada.", evidence_ids=[evidence[0]])
            return result, model

        monkeypatch.setattr(worker, "call_structured", answer)
        with Session(make_engine()) as db:
            job = db.get(Job, uuid.UUID(question["job_id"]))
            assert job is not None
            job.status = "running"
            db.commit()
            process_copilot_job(db, job.id)
        result = owner.get(f"{base}/questions/{question['question_id']}")
        assert result.json()["status"] == "succeeded"


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
        other_org = create_org(outsider, other_csrf, "copilot-other")
        other_user_id = outsider.get("/api/v1/auth/session").json()["user"]["id"]
        _, other_findings, other_evidence = seed_targets(other_org, other_user_id)
        other_base = f"/api/v1/organizations/{other_org}/ai"
        other_chat = create_chat(outsider, other_base, other_csrf, other_findings[0], "normal")
        other_question = ask(outsider, other_base, other_csrf, other_chat["id"], "Outro tenant?")
        finish_question(monkeypatch, other_question, other_evidence[0])

        third = create_chat(owner, base, csrf, findings[1], "normal")
        third_question = ask(owner, base, csrf, third["id"], "Que memória posso usar?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(third["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(third_question["question_id"]))
            assert conversation is not None and turn is not None
            context, allowed, _ = build_copilot_context(db, conversation, turn)
        assert uuid.UUID(other_evidence[0]) not in allowed
        assert all(entry["question"] != "Outro tenant?" for entry in context["organization_memory"])
        finish_question(monkeypatch, third_question, evidence[1])
        outsider_question = outsider.get(
            f"{base}/copilot/questions/{first_question['question_id']}"
        )
        assert outsider_question.status_code == 404
        assert outsider.get(f"{base}/copilot/conversations/{first['id']}").status_code == 404


def test_organization_agent_uses_only_its_completed_audit_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The company chat spans audits but cannot cite another tenant's evidence."""
    with TestClient(app) as owner, TestClient(app) as outsider:
        csrf = login(owner, create_user(owner, "agent-owner"))
        org_id = create_org(owner, csrf, "agent-org")
        user_id = owner.get("/api/v1/auth/session").json()["user"]["id"]
        _, _, first_evidence = seed_targets(org_id, user_id)
        _, _, second_evidence = seed_targets(org_id, user_id)
        failed_run_id, _, failed_evidence = seed_targets(org_id, user_id)
        with Session(make_engine()) as db:
            failed_run = db.get(AuditRun, uuid.UUID(failed_run_id))
            assert failed_run is not None
            failed_run.status = "failed"
            db.commit()
        base = f"/api/v1/organizations/{org_id}/ai"
        created = owner.post(
            f"{base}/copilot/conversations", headers=csrf_headers(csrf),
            json={"scope": "organization", "mode": "normal"},
        )
        assert created.status_code == 201, created.text
        chat = created.json()
        assert chat["scope"] == "organization"
        assert chat["finding_id"] is None and chat["audit_id"] is None
        listed = owner.get(f"{base}/copilot/conversations", params={"scope": "organization"})
        assert [item["id"] for item in listed.json()["items"]] == [chat["id"]]
        question = ask(owner, base, csrf, chat["id"], "Quais compras duplicadas revisar?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(chat["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(question["question_id"]))
            assert conversation is not None and turn is not None
            context, allowed, _ = build_copilot_context(db, conversation, turn)
        assert len(context["target"]["findings"]) == 4
        assert {uuid.UUID(value) for value in first_evidence + second_evidence} <= allowed
        assert not {uuid.UUID(value) for value in failed_evidence} & allowed
        finish_question(monkeypatch, question, second_evidence[0])
        answer = owner.get(f"{base}/copilot/questions/{question['question_id']}")
        assert answer.json()["status"] == "succeeded"
        assert answer.json()["citations"][0]["evidence_id"] == second_evidence[0]

        followup_chat = owner.post(
            f"{base}/copilot/conversations", headers=csrf_headers(csrf),
            json={"scope": "organization", "mode": "normal"},
        ).json()
        followup = ask(owner, base, csrf, followup_chat["id"], "O que o agente já explicou?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(followup_chat["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(followup["question_id"]))
            assert conversation is not None and turn is not None
            context, allowed, _ = build_copilot_context(db, conversation, turn)
        assert context["organization_memory"][0]["answer"] == "Verifique o documento citado."
        assert uuid.UUID(second_evidence[0]) in allowed
        finish_question(monkeypatch, followup, second_evidence[0])

        temporary = owner.post(
            f"{base}/copilot/conversations", headers=csrf_headers(csrf),
            json={"scope": "organization", "mode": "temporary"},
        ).json()
        temp_question = ask(owner, base, csrf, temporary["id"], "Sem memória externa?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(temporary["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(temp_question["question_id"]))
            assert conversation is not None and turn is not None
            context, _, _ = build_copilot_context(db, conversation, turn)
        assert context["organization_memory"] == []
        finish_question(monkeypatch, temp_question, second_evidence[0])
        saved = owner.get(f"{base}/copilot/conversations", params={"scope": "organization"})
        assert {item["id"] for item in saved.json()["items"]} == {chat["id"], followup_chat["id"]}

        outsider_csrf = login(outsider, create_user(outsider, "agent-outsider"))
        other_org = create_org(outsider, outsider_csrf, "agent-other")
        other_user_id = outsider.get("/api/v1/auth/session").json()["user"]["id"]
        _, _, other_evidence = seed_targets(other_org, other_user_id)
        outsider_list = outsider.get(
            f"{base}/copilot/conversations", params={"scope": "organization"}
        )
        assert outsider_list.status_code == 404
        assert outsider.get(f"{base}/copilot/conversations/{chat['id']}").status_code == 404
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(chat["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(question["question_id"]))
            assert conversation is not None and turn is not None
            _, allowed, _ = build_copilot_context(db, conversation, turn)
        assert uuid.UUID(other_evidence[0]) not in allowed

        invalid = owner.post(
            f"{base}/copilot/conversations", headers=csrf_headers(csrf),
            json={"scope": "organization", "finding_id": str(uuid.uuid4()), "mode": "normal"},
        )
        assert invalid.status_code == 422


def test_organization_agent_limits_context_and_denies_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large tenants receive a bounded context; read-only members cannot start a chat."""
    with TestClient(app) as owner, TestClient(app) as viewer:
        csrf = login(owner, create_user(owner, "bounded-agent-owner"))
        viewer_email = create_user(viewer, "bounded-agent-viewer")
        viewer_csrf = login(viewer, viewer_email)
        org_id = create_org(owner, csrf, "bounded-agent-org")
        user_id = owner.get("/api/v1/auth/session").json()["user"]["id"]
        for _ in range(11):
            seed_targets(org_id, user_id)
        created = owner.post(
            f"/api/v1/organizations/{org_id}/users", headers=csrf_headers(csrf),
            json={"email": viewer_email, "role": "viewer"},
        )
        assert created.status_code == 201, created.text
        base = f"/api/v1/organizations/{org_id}/ai"
        denied = viewer.post(
            f"{base}/copilot/conversations", headers=csrf_headers(viewer_csrf),
            json={"scope": "organization", "mode": "temporary"},
        )
        assert denied.status_code == 403
        chat = owner.post(
            f"{base}/copilot/conversations", headers=csrf_headers(csrf),
            json={"scope": "organization", "mode": "temporary"},
        ).json()
        question = ask(owner, base, csrf, chat["id"], "Quais compras duplicadas?")
        with Session(make_engine()) as db:
            conversation = db.get(CopilotConversation, uuid.UUID(chat["id"]))
            turn = db.get(CopilotTurn, uuid.UUID(question["question_id"]))
            assert conversation is not None and turn is not None
            context, allowed, partial = build_copilot_context(db, conversation, turn)
        assert len(context["target"]["findings"]) == 20
        assert len(allowed) == 20
        assert partial is True
        finish_question(monkeypatch, question, str(next(iter(allowed))))


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
            json={"temporary_default": True, "memory_turn_limit": 0,
                  "instructions": "Explique os números de forma objetiva."},
        )
        assert policy.status_code == 200
        assert policy.json()["instructions"] == "Explique os números de forma objetiva."
        assert analyst.get(f"{base}/copilot/policy").json()["temporary_default"] is True
        assert analyst.put(
            f"{base}/copilot/policy", headers=csrf_headers(analyst_csrf),
            json={"temporary_default": False, "memory_turn_limit": 10},
        ).status_code == 403
        assert owner.put(
            f"{base}/copilot/policy", headers=csrf_headers(owner_csrf),
            json={"temporary_default": True, "memory_turn_limit": 0,
                  "instructions": "x" * 2001},
        ).status_code == 422
        preserved = owner.put(
            f"{base}/copilot/policy", headers=csrf_headers(owner_csrf),
            json={"temporary_default": True, "memory_turn_limit": 0},
        )
        assert preserved.json()["instructions"] == "Explique os números de forma objetiva."
        other_org = create_org(owner, owner_csrf, "copilot-other-instructions")
        other_policy = owner.get(f"/api/v1/organizations/{other_org}/ai/copilot/policy")
        assert other_policy.json()["instructions"] == ""
        with Session(make_engine()) as db:
            customized = system_message_for_organization(db, uuid.UUID(org_id), "Regras fixas.")
            standard = system_message_for_organization(db, uuid.UUID(other_org), "Regras fixas.")
        assert "Explique os números de forma objetiva." in customized
        assert "nunca dispensam evidências" in customized
        assert standard == "Regras fixas."
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

        rejected = create_chat(analyst, base, analyst_csrf, findings[0], "normal")
        decision_path = f"{base}/copilot/conversations/{rejected['id']}"
        assert owner.post(
            f"{decision_path}/reject", headers=csrf_headers(owner_csrf)
        ).status_code == 200
        assert owner.post(
            f"{decision_path}/reject", headers=csrf_headers(owner_csrf)
        ).status_code == 200
        assert owner.post(
            f"{decision_path}/approve", headers=csrf_headers(owner_csrf)
        ).status_code == 409
        listed = analyst.get(f"{base}/copilot/conversations", params={"finding_id": findings[0]})
        assert rejected["id"] not in [item["id"] for item in listed.json()["items"]]

        temporary = create_chat(analyst, base, analyst_csrf, findings[0], "temporary")
        with Session(make_engine()) as db:
            chat = db.get(CopilotConversation, uuid.UUID(temporary["id"]))
            assert chat is not None
            chat.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()
            assert purge_expired_temporary(db) == 1
        assert analyst.get(f"{base}/copilot/conversations/{temporary['id']}").status_code == 404


def test_copilot_rejects_invalid_input_and_revoked_membership() -> None:
    with TestClient(app) as owner, TestClient(app) as analyst, TestClient(app) as viewer:
        owner_csrf = login(owner, create_user(owner, "copilot-auth-owner"))
        analyst_email = create_user(analyst, "copilot-auth-analyst")
        analyst_csrf = login(analyst, analyst_email)
        viewer_email = create_user(viewer, "copilot-auth-viewer")
        viewer_csrf = login(viewer, viewer_email)
        org_id = create_org(owner, owner_csrf, "copilot-auth")
        owner_id = owner.get("/api/v1/auth/session").json()["user"]["id"]
        _, findings, _ = seed_targets(org_id, owner_id)
        base = f"/api/v1/organizations/{org_id}/ai/copilot"
        members = f"/api/v1/organizations/{org_id}/users"
        analyst_member = owner.post(
            members, headers=csrf_headers(owner_csrf),
            json={"email": analyst_email, "role": "analyst"},
        ).json()
        owner.post(
            members, headers=csrf_headers(owner_csrf),
            json={"email": viewer_email, "role": "viewer"},
        )
        assert viewer.get(f"{base}/policy").status_code == 200
        assert viewer.post(
            f"{base}/conversations", headers=csrf_headers(viewer_csrf),
            json={"finding_id": findings[0], "mode": "normal"},
        ).status_code == 403
        assert analyst.post(
            f"{base}/conversations",
            json={"finding_id": findings[0], "mode": "normal"},
        ).status_code == 403
        assert analyst.post(
            f"{base}/conversations", headers=csrf_headers(analyst_csrf, "https://evil.example"),
            json={"finding_id": findings[0], "mode": "normal"},
        ).status_code == 403
        assert analyst.post(
            f"{base}/conversations", headers=csrf_headers(analyst_csrf),
            json={"finding_id": findings[0], "audit_id": str(uuid.uuid4()), "mode": "normal"},
        ).status_code == 422
        assert analyst.post(
            f"{base}/conversations", headers=csrf_headers(analyst_csrf),
            json={"finding_id": str(uuid.uuid4()), "mode": "temporary"},
        ).status_code == 422
        chat = create_chat(analyst, f"/api/v1/organizations/{org_id}/ai", analyst_csrf,
                           findings[0], "normal")
        changed = owner.patch(
            f"{members}/{analyst_member['user_id']}", headers=csrf_headers(owner_csrf),
            json={"status": "inactive"},
        )
        assert changed.status_code == 200
        assert analyst.get(f"{base}/conversations/{chat['id']}").status_code == 401
        login(analyst, analyst_email)
        assert analyst.get(f"{base}/conversations/{chat['id']}").status_code == 404


def test_copilot_result_rejects_unverified_references_and_links() -> None:
    allowed = uuid.uuid4()
    unknown = uuid.uuid4()
    with pytest.raises(ValueError):
        CopilotResult(answer="Evidência não fornecida", evidence_ids=[unknown]).validate_evidence(
            {allowed}
        )
    with pytest.raises(ValueError):
        CopilotResult(
            answer="Veja https://example.com", evidence_ids=[allowed]
        ).validate_evidence({allowed})
