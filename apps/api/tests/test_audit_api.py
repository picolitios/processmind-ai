import io
import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_audit_config_coordination import apply_through_private_api
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import settings
from app.db.engine import make_engine
from app.features.audit.models import AuditConfiguration, AuditRun
from app.features.audit.worker import process_audit_job
from app.features.identity import client as identity_client
from app.features.identity.introspection import IntrospectionResult, MembershipResult
from app.features.identity.models import User
from app.features.identity.routes import require_membership as require_local_membership
from app.features.identity.security import authenticate_token
from app.features.ingestion.models import ImportBatch, Job
from app.features.ingestion.worker import run_once
from app.identity_app import app as identity_app
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


@pytest.mark.parametrize(
    ("config_mode", "write_mode"),
    [("legacy", "database"), ("owned", "database"), ("owned", "coordinated")],
)
def test_audit_snapshot_stays_version_consistent_during_settings_update(
    config_mode: str, write_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "audit_config_mode", config_mode)
    monkeypatch.setattr(settings, "audit_config_write_mode", write_mode)
    with TestClient(app) as owner, TestClient(app) as auditor, TestClient(app) as audit_private:
        if write_mode == "coordinated":
            apply_through_private_api(monkeypatch, audit_private)
        owner_email = create_user(owner, "snapshot-owner")
        csrf = login(owner, owner_email)
        org_id = create_org(owner, csrf, "snapshot-org")
        cookie = owner.cookies.get("pm_session")
        assert cookie is not None
        auditor.cookies.set("pm_session", cookie)
        with Session(make_engine()) as db:
            owner_id = db.scalar(select(User.id).where(User.email == owner_email))
            assert owner_id is not None
            batch = ImportBatch(
                organization_id=uuid.UUID(org_id),
                uploader_id=owner_id,
                sha256=uuid.uuid4().hex,
                original_name="snapshot.csv",
                private_storage_key=uuid.uuid4().hex,
                file_format="csv",
                status="succeeded",
                mapping={"columns": {}},
            )
            db.add(batch)
            db.commit()
            batch_id = batch.id

        barrier = threading.Barrier(2)
        base = f"/api/v1/organizations/{org_id}"

        def change_settings() -> int:
            barrier.wait(timeout=5)
            response = owner.patch(
                base,
                headers=csrf_headers(csrf),
                json={"amount_limits": {"BRL": "100.00"}, "delay_window_days": 30},
            )
            return response.status_code

        def create_audit() -> tuple[int, str]:
            barrier.wait(timeout=5)
            response = auditor.post(
                f"{base}/audits",
                headers={**csrf_headers(csrf), "Idempotency-Key": uuid.uuid4().hex},
                json={"import_ids": [str(batch_id)]},
            )
            return response.status_code, response.json().get("id", "")

        # The row lock must serialize the configuration update and audit snapshot transaction.
        with ThreadPoolExecutor(max_workers=2) as pool:
            settings_future = pool.submit(change_settings)
            audit_future = pool.submit(create_audit)
            settings_status = settings_future.result()
            audit_status, audit_id = audit_future.result()
        assert settings_status == 200
        assert audit_status == 202
        with Session(make_engine()) as db:
            run = db.get(AuditRun, uuid.UUID(audit_id))
            audit_config = db.get(AuditConfiguration, uuid.UUID(org_id))
            assert run is not None
            assert audit_config is not None
            assert audit_config.settings_version == 2
            assert audit_config.amount_limits == {"BRL": "100.00"}
            assert audit_config.delay_window_days == 30
            snapshot = run.config_snapshot
            job_id = run.job_id
        assert snapshot in (
            {"settings_version": 1, "amount_limits": {}, "delay_window_days": 90},
            {
                "settings_version": 2,
                "amount_limits": {"BRL": "100.00"},
                "delay_window_days": 30,
            },
        )
        assert job_id is not None
        # Finish this test's queued job so later worker tests cannot claim synthetic input.
        with Session(make_engine()) as db:
            job = db.get(Job, job_id)
            assert job is not None
            job.status = "running"
            db.commit()
            process_audit_job(db, job_id)


def test_remote_authorization_uses_owned_snapshot_during_coordinated_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "audit_config_mode", "owned")
    monkeypatch.setattr(settings, "audit_config_write_mode", "coordinated")
    with (
        TestClient(identity_app) as identity,
        TestClient(app) as business,
        TestClient(app) as audit_private,
    ):
        apply_through_private_api(monkeypatch, audit_private)
        csrf = login(identity, create_user(identity, "remote-snapshot-owner"))
        org_id = create_org(identity, csrf, "remote-snapshot-org")
        cookie = identity.cookies.get("pm_session")
        assert cookie is not None
        business.cookies.set("pm_session", cookie)
        with Session(make_engine()) as db:
            owner = authenticate_token(db, cookie)
            batch = ImportBatch(
                organization_id=uuid.UUID(org_id),
                uploader_id=owner.user.id,
                sha256=uuid.uuid4().hex,
                original_name="remote-snapshot.csv",
                private_storage_key=uuid.uuid4().hex,
                file_format="csv",
                status="succeeded",
                mapping={"columns": {}},
            )
            db.add(batch)
            db.commit()
            batch_id = batch.id

        def introspect(token: str, csrf_token: str | None = None) -> IntrospectionResult:
            with Session(make_engine()) as db:
                auth = authenticate_token(db, token)
                return IntrospectionResult(
                    user_id=auth.user.id,
                    session_id=auth.session.id,
                    csrf_valid=csrf_token == csrf,
                )

        def authorize(token: str, requested_org: uuid.UUID) -> MembershipResult:
            with Session(make_engine()) as db:
                auth = authenticate_token(db, token)
                _, member = require_local_membership(db, auth, requested_org)
                return MembershipResult(
                    membership_id=member.id,
                    user_id=member.user_id,
                    organization_id=member.organization_id,
                    role=member.role,
                )

        monkeypatch.setattr(identity_client, "introspect_remote", introspect)
        monkeypatch.setattr(identity_client, "authorize_membership_remote", authorize)
        monkeypatch.setattr(settings, "business_auth_mode", "identity")
        barrier = threading.Barrier(2)
        base = f"/api/v1/organizations/{org_id}"

        def change_settings() -> int:
            barrier.wait(timeout=5)
            response = identity.patch(
                base,
                headers=csrf_headers(csrf),
                json={"amount_limits": {"BRL": "150.00"}, "delay_window_days": 15},
            )
            return response.status_code

        def create_audit() -> tuple[int, str]:
            barrier.wait(timeout=5)
            response = business.post(
                f"{base}/audits",
                headers={**csrf_headers(csrf), "Idempotency-Key": uuid.uuid4().hex},
                json={"import_ids": [str(batch_id)]},
            )
            return response.status_code, response.json().get("id", "")

        with ThreadPoolExecutor(max_workers=2) as pool:
            settings_status = pool.submit(change_settings)
            audit_result = pool.submit(create_audit)
            assert settings_status.result() == 200
            audit_status, audit_id = audit_result.result()
        assert audit_status == 202
        with Session(make_engine()) as db:
            run = db.get(AuditRun, uuid.UUID(audit_id))
            assert run is not None
            assert run.config_snapshot in (
                {"settings_version": 1, "amount_limits": {}, "delay_window_days": 90},
                {
                    "settings_version": 2,
                    "amount_limits": {"BRL": "150.00"},
                    "delay_window_days": 15,
                },
            )
            assert run.job_id is not None
            job = db.get(Job, run.job_id)
            assert job is not None
            job.status = "running"
            db.commit()
            process_audit_job(db, job.id)


def test_owned_audit_configuration_missing_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "audit_config_mode", "owned")
    with TestClient(app) as client:
        email = create_user(client, "missing-config-owner")
        token = login(client, email)
        org_id = create_org(client, token, "missing-config-org")
        with Session(make_engine()) as db:
            config = db.get(AuditConfiguration, uuid.UUID(org_id))
            assert config is not None
            user_id = db.scalar(select(User.id).where(User.email == email))
            assert user_id is not None
            batch = ImportBatch(
                organization_id=uuid.UUID(org_id),
                uploader_id=user_id,
                sha256=uuid.uuid4().hex,
                original_name="missing-config.csv",
                private_storage_key=uuid.uuid4().hex,
                file_format="csv",
                status="succeeded",
                mapping={"columns": {}},
            )
            db.add(batch)
            db.delete(config)
            db.commit()
            batch_id = batch.id
        audit_response = client.post(
            f"/api/v1/organizations/{org_id}/audits",
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [str(batch_id)]},
        )
        assert audit_response.status_code == 503
        assert audit_response.json()["code"] == "audit_configuration_missing"
        response = client.patch(
            f"/api/v1/organizations/{org_id}",
            headers=csrf_headers(token),
            json={"delay_window_days": 10},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "audit_configuration_missing"


def test_audit_idempotency_findings_and_tenant_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with TestClient(app) as owner, TestClient(app) as outsider, TestClient(app) as viewer:
        token = login(owner, create_user(owner, "audit-owner"))
        other_token = login(outsider, create_user(outsider, "audit-other"))
        viewer_email = create_user(viewer, "audit-viewer")
        viewer_token = login(viewer, viewer_email)
        org_id = create_org(owner, token, "audit-org")
        other_org_id = create_org(outsider, other_token, "audit-other-org")
        base = f"/api/v1/organizations/{org_id}"
        assert (
            owner.post(
                f"{base}/users",
                headers=csrf_headers(token),
                json={"email": viewer_email, "role": "viewer"},
            ).status_code
            == 201
        )
        csv_bytes = (
            b"purchase_id,supplier_id,purchase_date,product_id,quantity,unit_price,currency,"
            b"total_amount,expected_delivery_date,actual_delivery_date\n"
            b"P-1,S-1,2025-01-01,SKU-1,2,10,BRL,20,2025-01-05,2025-01-05\n"
            b"P-2,S-1,2025-01-01,SKU-1,2,10,BRL,20,2025-01-05,2025-01-05\n"
            b"P-3,S-2,2025-01-02,SKU-2,0,10,BRL,0,2025-01-05,2025-01-05\n"
            b"P-4,S-3,2025-01-03,SKU-3,1,10,BRL,10,2025-01-05,2025-01-10\n"
        )
        uploaded = owner.post(
            f"{base}/imports", headers=csrf_headers(token), files={"file": ("audit.csv", csv_bytes)}
        )
        assert uploaded.status_code == 201, uploaded.text
        import_id = uploaded.json()["id"]
        headers = csv_bytes.decode().splitlines()[0].split(",")
        mapping = {field: field for field in headers}
        assert (
            owner.post(
                f"{base}/imports/{import_id}/confirm",
                headers=csrf_headers(token),
                json={"columns": mapping},
            ).status_code
            == 202
        )
        assert run_once()
        other_base = f"/api/v1/organizations/{other_org_id}"
        other_upload = outsider.post(
            f"{other_base}/imports",
            headers=csrf_headers(other_token),
            files={"file": ("other.csv", csv_bytes)},
        )
        assert other_upload.status_code == 201
        other_import_id = other_upload.json()["id"]
        assert (
            outsider.post(
                f"{other_base}/imports/{other_import_id}/confirm",
                headers=csrf_headers(other_token),
                json={"columns": mapping},
            ).status_code
            == 202
        )
        assert run_once()

        key = uuid.uuid4().hex
        request_headers = {**csrf_headers(token), "Idempotency-Key": key}
        created = owner.post(
            f"{base}/audits", headers=request_headers, json={"import_ids": [import_id]}
        )
        assert created.status_code == 202, created.text
        audit_id = created.json()["id"]
        replay = owner.post(
            f"{base}/audits", headers=request_headers, json={"import_ids": [import_id]}
        )
        assert replay.status_code == 202 and replay.json()["id"] == audit_id
        assert outsider.get(f"{base}/audits/{audit_id}").status_code == 404
        assert outsider.get(f"{base}/findings").status_code == 404
        assert viewer.get(f"{base}/audits/{audit_id}").status_code == 200
        assert (
            viewer.post(
                f"{base}/audits",
                headers={**csrf_headers(viewer_token), "Idempotency-Key": uuid.uuid4().hex},
                json={"import_ids": [import_id]},
            ).status_code
            == 403
        )
        assert (
            owner.post(
                f"{base}/audits",
                headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
                json={"import_ids": [str(uuid.uuid4())]},
            ).status_code
            == 422
        )
        assert (
            owner.post(
                f"{base}/audits",
                headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
                json={"import_ids": [other_import_id]},
            ).status_code
            == 422
        )

        assert run_once()
        result = owner.get(f"{base}/audits/{audit_id}").json()
        assert result["status"] == "succeeded"
        assert (
            owner.post(
                f"{base}/audits", headers=request_headers, json={"import_ids": [import_id]}
            ).json()["id"]
            == audit_id
        )
        findings = owner.get(f"{base}/findings", params={"audit_id": audit_id}).json()["items"]
        assert result["finding_count"] == len(findings)
        assert {item["rule_code"] for item in findings} == {
            "DUPLICATE",
            "INVALID_QUANTITY",
            "INCOMPLETE_RECORD",
            "LATE_DELIVERY",
        }
        duplicate = next(item for item in findings if item["rule_code"] == "DUPLICATE")
        assert duplicate["subject_key"] == "product:SKU-1"
        assert "SKU-1" in duplicate["subject_label"]
        late = next(item for item in findings if item["rule_code"] == "LATE_DELIVERY")
        assert late["subject_key"] == "product:SKU-3"
        assert len(duplicate["evidence"]) == 2
        purchases = [item["data"]["purchase"] for item in duplicate["evidence"]]
        assert {item["purchase_id"] for item in purchases} == {"P-1", "P-2"}
        assert {item["product_id"] for item in purchases} == {"SKU-1"}
        assert {item["supplier_id"] for item in purchases} == {"S-1"}
        assert {item["declared_total"] for item in purchases} == {"20.00"}
        assert {item["import_id"] for item in purchases} == {import_id}
        detail = owner.get(f"{base}/findings/{duplicate['id']}")
        assert detail.status_code == 200
        assert detail.json()["evidence"] == duplicate["evidence"]
        assert outsider.get(f"{base}/findings/{duplicate['id']}").status_code == 404
        assert len(owner.get(f"{base}/findings", params={"severity": "high"}).json()["items"]) == 1
        first_page = owner.get(f"{base}/findings", params={"audit_id": audit_id, "limit": 1}).json()
        assert first_page["next_cursor"]
        next_page = owner.get(
            f"{base}/findings",
            params={"audit_id": audit_id, "limit": 1, "cursor": first_page["next_cursor"]},
        ).json()
        assert next_page["items"][0]["id"] != first_page["items"][0]["id"]

        evidence_id = duplicate["evidence"][0]["id"]
        ai_base = f"{base}/ai/analyses"
        ai_headers = {**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex}
        created_ai = owner.post(ai_base, headers=ai_headers, json={"finding_id": duplicate["id"]})
        assert created_ai.status_code == 202, created_ai.text
        assert (
            owner.post(ai_base, headers=ai_headers, json={"finding_id": duplicate["id"]}).json()
            == created_ai.json()
        )
        assert (
            owner.post(ai_base, headers=ai_headers, json={"audit_id": audit_id}).status_code == 409
        )
        assert (
            outsider.post(
                ai_base,
                headers={**csrf_headers(other_token), "Idempotency-Key": uuid.uuid4().hex},
                json={"finding_id": duplicate["id"]},
            ).status_code
            == 404
        )
        assert (
            viewer.post(
                ai_base,
                headers={**csrf_headers(viewer_token), "Idempotency-Key": uuid.uuid4().hex},
                json={"finding_id": duplicate["id"]},
            ).status_code
            == 403
        )

        response = {
            "summary": "Possível duplicidade de compras.",
            "possible_causes": ["Registro repetido."],
            "suggested_checks": ["Conferir os pedidos originais."],
            "corrective_actions": ["Revisar antes de pagar."],
            "evidence_ids": [evidence_id],
        }

        def fake_ollama(request: object, timeout: int) -> io.BytesIO:
            assert timeout == settings.ollama_timeout_seconds
            body = json.loads(request.data)  # type: ignore[attr-defined]
            assert body["stream"] is False
            assert body["format"]["type"] == "object"
            if body["messages"][1]["content"].find(str(duplicate["id"])) != -1:
                assert '"purchase_id": "P-1"' in body["messages"][1]["content"]
                assert '"purchase_id": "P-2"' in body["messages"][1]["content"]
            return io.BytesIO(
                json.dumps(
                    {
                        "done": True,
                        "model": "test-model",
                        "message": {"content": json.dumps(response)},
                    }
                ).encode()
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_ollama)
        assert run_once()
        analysis_id = created_ai.json()["analysis_id"]
        ai_result = owner.get(f"{ai_base}/{analysis_id}").json()
        assert ai_result["status"] == "succeeded"
        assert ai_result["evidence_ids"] == [evidence_id]
        assert outsider.get(f"{ai_base}/{analysis_id}").status_code == 404
        assert viewer.get(f"{ai_base}/{analysis_id}").status_code == 200

        audit_ai = owner.post(
            ai_base,
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"audit_id": audit_id},
        )
        assert audit_ai.status_code == 202
        assert run_once()
        assert (
            owner.get(f"{ai_base}/{audit_ai.json()['analysis_id']}").json()["status"] == "succeeded"
        )

        response["evidence_ids"] = [str(uuid.uuid4())]
        invalid = owner.post(
            ai_base,
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"finding_id": duplicate["id"]},
        )
        assert invalid.status_code == 202
        assert run_once()
        invalid_id = invalid.json()["analysis_id"]
        invalid_result = owner.get(f"{ai_base}/{invalid_id}").json()
        assert invalid_result["status"] == "failed" and invalid_result["evidence_ids"] == []

        def unavailable(request: object, timeout: int) -> io.BytesIO:
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(urllib.request, "urlopen", unavailable)
        offline = owner.post(
            ai_base,
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"finding_id": duplicate["id"]},
        )
        assert offline.status_code == 202
        assert run_once()
        offline_id = offline.json()["analysis_id"]
        offline_result = owner.get(f"{ai_base}/{offline_id}").json()
        assert offline_result["status"] == "failed"
        assert "Ollama indisponível" in offline_result["limitation"]
        assert owner.get(f"{base}/audits/{audit_id}").json()["status"] == "succeeded"

        clean_bytes = b"\n".join(csv_bytes.splitlines()[:2]) + b"\n"
        clean_import = owner.post(
            f"{base}/imports",
            headers=csrf_headers(token),
            files={"file": ("clean.csv", clean_bytes)},
        )
        assert clean_import.status_code == 201
        clean_import_id = clean_import.json()["id"]
        assert (
            owner.post(
                f"{base}/imports/{clean_import_id}/confirm",
                headers=csrf_headers(token),
                json={"columns": mapping},
            ).status_code
            == 202
        )
        assert run_once()
        clean_audit = owner.post(
            f"{base}/audits",
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [clean_import_id]},
        )
        assert clean_audit.status_code == 202
        assert run_once()
        assert owner.get(f"{base}/audits/{clean_audit.json()['id']}").json()["finding_count"] == 0
        no_evidence = owner.post(
            ai_base,
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"audit_id": clean_audit.json()["id"]},
        )
        assert no_evidence.status_code == 202
        assert run_once()
        empty_result = owner.get(f"{ai_base}/{no_evidence.json()['analysis_id']}").json()
        assert empty_result["status"] == "failed"
        assert "Dados insuficientes" in empty_result["limitation"]
