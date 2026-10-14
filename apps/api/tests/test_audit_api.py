import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import settings
from app.features.ingestion.worker import run_once
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


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
        assert len(duplicate["evidence"]) == 2
        assert owner.get(f"{base}/findings/{duplicate['id']}").status_code == 200
        assert outsider.get(f"{base}/findings/{duplicate['id']}").status_code == 404
        assert len(owner.get(f"{base}/findings", params={"severity": "high"}).json()["items"]) == 1
        first_page = owner.get(f"{base}/findings", params={"audit_id": audit_id, "limit": 1}).json()
        assert first_page["next_cursor"]
        next_page = owner.get(
            f"{base}/findings",
            params={"audit_id": audit_id, "limit": 1, "cursor": first_page["next_cursor"]},
        ).json()
        assert next_page["items"][0]["id"] != first_page["items"][0]["id"]
