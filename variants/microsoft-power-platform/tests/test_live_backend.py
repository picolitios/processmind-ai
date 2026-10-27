"""Optional end-to-end proof against a dedicated migrated PostgreSQL database."""

import os
import uuid
from pathlib import Path

import pytest

from processmind_power.client import IntegrationError, ProcessMindClient


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="dedicated test database required")
def test_local_journey_uses_real_import_audit_and_copilot_boundaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Run real ProcessMind HTTP/workers; substitute only optional Ollama inference."""
    from app.core.config import settings
    from app.features.copilot import worker as copilot_worker
    from app.features.copilot.schemas import CopilotResult
    from app.features.ingestion.worker import run_once
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "audit_dispatch_mode", "database")
    monkeypatch.setattr(settings, "business_auth_mode", "database")
    monkeypatch.setattr(settings, "audit_config_mode", "legacy")
    monkeypatch.setattr(settings, "audit_config_write_mode", "database")

    csv_bytes = (
        b"purchase_id,supplier_id,purchase_date,product_id,quantity,unit_price,currency,"
        b"total_amount,expected_delivery_date,actual_delivery_date\n"
        b"P-1,S-1,2025-01-01,SKU-1,2,10,BRL,20,2025-01-05,2025-01-05\n"
        b"P-2,S-1,2025-01-01,SKU-1,2,10,BRL,20,2025-01-05,2025-01-05\n"
    )
    with TestClient(app, base_url="http://localhost:5173") as http:
        email = f"power-demo-{uuid.uuid4().hex}@example.com"
        registered = http.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "strong-test-passphrase"},
        )
        assert registered.status_code == 201, registered.text
        login = http.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "strong-test-passphrase"},
        )
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf_token"]
        organization = http.post(
            "/api/v1/organizations",
            headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
            json={"name": "Power demo", "slug": f"power-{uuid.uuid4().hex[:12]}"},
        )
        assert organization.status_code == 201, organization.text
        org_id = uuid.UUID(organization.json()["id"])
        api = ProcessMindClient("http://localhost:5173", org_id, client=http)
        api.login(email, "strong-test-passphrase")

        uploaded = http.post(
            f"/api/v1/organizations/{org_id}/imports",
            headers={"Origin": "http://localhost:5173", "X-CSRF-Token": api.csrf or ""},
            files={"file": ("power-demo.csv", csv_bytes)},
        )
        assert uploaded.status_code == 201, uploaded.text
        import_id = uuid.UUID(uploaded.json()["id"])
        columns = csv_bytes.decode().splitlines()[0].split(",")
        confirmed = http.post(
            f"/api/v1/organizations/{org_id}/imports/{import_id}/confirm",
            headers={"Origin": "http://localhost:5173", "X-CSRF-Token": api.csrf or ""},
            json={"columns": {column: column for column in columns}},
        )
        assert confirmed.status_code == 202, confirmed.text
        assert run_once()

        requested = api.request_audit([import_id], uuid.uuid4().hex)
        assert requested.status == "queued"
        assert run_once()
        completed = api.audit(requested.id)
        assert completed.status == "succeeded"
        findings = api.findings(completed.id)
        duplicate = next(item for item in findings if item.rule_code == "DUPLICATE")
        assert duplicate.evidence
        assert completed.finding_count == len(findings)

        conversation_id = api.create_conversation(completed.id)
        question_id = api.ask(conversation_id, "Quais compras devo revisar?", uuid.uuid4().hex)
        evidence_id = duplicate.evidence[0].id

        def model_answer(_context: object, _model: str, _schema: object, _system: str):
            return CopilotResult(answer="Revise as compras duplicadas citadas.",
                                 evidence_ids=[evidence_id]), "test-model"

        monkeypatch.setattr(copilot_worker, "call_structured", model_answer)
        assert run_once()
        answer = api.question(question_id)
        assert answer.status == "succeeded"
        assert answer.citations[0].evidence_id == evidence_id
        assert answer.citations[0].audit_id == completed.id

        with TestClient(app, base_url="http://localhost:5173") as outsider_http:
            outsider_email = f"outsider-{uuid.uuid4().hex}@example.com"
            created = outsider_http.post("/api/v1/auth/register", json={
                "email": outsider_email, "password": "strong-test-passphrase"})
            assert created.status_code == 201
            outsider = ProcessMindClient("http://localhost:5173", org_id,
                                        client=outsider_http)
            outsider.login(outsider_email, "strong-test-passphrase")
            with pytest.raises(IntegrationError, match="not_found"):
                outsider.audit(completed.id)
