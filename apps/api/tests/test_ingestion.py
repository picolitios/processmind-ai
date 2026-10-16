import os
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from openpyxl import Workbook
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import settings
from app.core.errors import ApiError
from app.features.ingestion.parsing import bounded_rows, normalize, preview
from app.features.ingestion.worker import run_once
from app.main import app

HEADERS = (
    "purchase_id,supplier_id,purchase_date,product_id,quantity,unit_price,currency,total_amount\n"
)
VALID = "P-1,S-1,2025-01-01,SKU-1,2,10.00,BRL,20.00\n"
INVALID = "P-2,S-1,2025-01-02,SKU-1,bad,10.00,BRL,20.00\n"
REPEATED_ID = "P-1,S-2,2025-01-03,SKU-2,1,10.00,BRL,10.00\n"


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL required")
def test_concurrent_upload_deduplication_and_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with TestClient(app) as first, TestClient(app) as second:
        csrf = login(first, create_user(first, "dedup-owner"))
        org_id = create_org(first, csrf, "dedup-org")
        cookie = first.cookies.get("pm_session")
        assert cookie is not None
        second.cookies.set("pm_session", cookie)
        path = f"/api/v1/organizations/{org_id}/imports"

        def upload_pair(payload: bytes, key: str | None = None) -> list[Response]:
            # Release both clients together so the database lock arbitrates concurrent requests.
            barrier = threading.Barrier(2)

            def upload(client: TestClient) -> Response:
                barrier.wait(timeout=5)
                headers = csrf_headers(csrf)
                if key:
                    headers["Idempotency-Key"] = key
                return client.post(path, headers=headers, files={"file": ("same.csv", payload)})

            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(upload, (first, second)))

        duplicate = upload_pair((HEADERS + VALID).encode())
        assert sorted(response.status_code for response in duplicate) == [201, 409]
        assert any(response.json().get("code") == "duplicate_file" for response in duplicate)

        idempotent = upload_pair((HEADERS + VALID.replace("P-1", "P-3")).encode(), uuid.uuid4().hex)
        assert [response.status_code for response in idempotent] == [201, 201]
        assert idempotent[0].json()["id"] == idempotent[1].json()["id"]


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL required")
def test_concurrent_import_jobs_remain_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    batches: list[tuple[TestClient, str, str]] = []
    with TestClient(app) as first, TestClient(app) as second:
        for client in (first, second):
            email = create_user(client, "concurrent-import")
            token = login(client, email)
            org_id = create_org(client, token, "concurrent-org")
            base = f"/api/v1/organizations/{org_id}/imports"
            uploaded = client.post(
                base,
                headers=csrf_headers(token),
                files={"file": ("concurrent.csv", (HEADERS + VALID).encode())},
            )
            assert uploaded.status_code == 201, uploaded.text
            batch_id = uploaded.json()["id"]
            confirmed = client.post(
                f"{base}/{batch_id}/confirm",
                headers=csrf_headers(token),
                json={"columns": {field: field for field in HEADERS.strip().split(",")}},
            )
            assert confirmed.status_code == 202, confirmed.text
            batches.append((client, org_id, batch_id))
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert all(pool.map(lambda _: run_once(), range(2)))
        for client, org_id, batch_id in batches:
            base = f"/api/v1/organizations/{org_id}"
            result = client.get(f"{base}/imports/{batch_id}")
            assert result.status_code == 200
            assert result.json()["status"] == "succeeded"
            assert result.json()["row_count"] == 1
            purchases = client.get(
                f"{base}/purchases", params={"import_id": batch_id}
            ).json()["items"]
            assert len(purchases) == 1
            other_client = second if client is first else first
            assert other_client.get(f"{base}/imports/{batch_id}").status_code == 404


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL required")
def test_upload_confirm_worker_rows_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with TestClient(app) as first, TestClient(app) as second:
        first_email = create_user(first, "importer")
        second_email = create_user(second, "other-importer")
        token = login(first, first_email)
        login(second, second_email)
        org_id = create_org(first, token, "import-org")
        other_org = create_org(
            second, second.get("/api/v1/auth/session").json()["csrf_token"], "other-org"
        )
        path = f"/api/v1/organizations/{org_id}/imports"
        payload = (HEADERS + VALID + INVALID + REPEATED_ID).encode()
        response = first.post(
            path,
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            files={"file": ("purchases.csv", payload, "text/csv")},
        )
        assert response.status_code == 201, response.text
        import_id = response.json()["id"]
        assert second.get(f"{path}/{import_id}").status_code == 404
        assert first.get(f"/api/v1/organizations/{other_org}/imports").status_code == 404
        assert (
            first.post(
                path, headers=csrf_headers(token), files={"file": ("same.csv", payload)}
            ).status_code
            == 409
        )
        assert first.get(f"{path}/{import_id}/preview").json()["rows"] == [
            VALID.strip().split(","),
            INVALID.strip().split(","),
            REPEATED_ID.strip().split(","),
        ]
        mapping = {key: key for key in HEADERS.strip().split(",")}
        confirmed = first.post(
            f"{path}/{import_id}/confirm",
            headers=csrf_headers(token),
            json={"columns": mapping},
        )
        assert confirmed.status_code == 202, confirmed.text
        assert run_once()
        summary = first.get(f"{path}/{import_id}").json()
        assert summary["status"] == "succeeded"
        assert (summary["row_count"], summary["error_count"]) == (3, 2)
        rows = first.get(f"{path}/{import_id}/rows").json()["items"]
        assert len(rows) == 3
        assert rows[0]["errors"] == []
        assert rows[1]["errors"][0]["field"] == "quantity"
        assert rows[2]["errors"][0]["code"] == "duplicate_id"
        purchases = first.get(
            f"/api/v1/organizations/{org_id}/purchases", params={"import_id": import_id}
        ).json()["items"]
        assert len(purchases) == 1
        assert purchases[0]["total_amount"] == "20.00"
        assert second.get(f"{path}/{import_id}/rows").status_code == 404


def test_preview_rejects_malicious_and_malformed_files(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_bytes(b"PK\x03\x04pretend-csv")
    with pytest.raises(ApiError):
        preview(bad_csv, "csv")

    formula = tmp_path / "formula.xlsx"
    book = Workbook()
    book.active.append(["purchase_id", "quantity"])
    book.active.append(["P-1", "=1+1"])
    book.save(formula)
    with pytest.raises(ApiError):
        preview(formula, "xlsx")

    external = tmp_path / "external.xlsx"
    with zipfile.ZipFile(external, "w") as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("xl/workbook.xml", "x")
        archive.writestr("xl/externalLinks/externalLink1.xml", "x")
    with pytest.raises(ApiError):
        preview(external, "xlsx")


def test_limits_and_numeric_overflow() -> None:
    with pytest.raises(ApiError) as failure:
        list(bounded_rows(iter([["x"]] * 50_002)))
    assert failure.value.code == "too_many_rows"
    raw = dict(zip(HEADERS.strip().split(","), VALID.strip().split(","), strict=True))
    raw["quantity"] = "1e100"
    _, errors = normalize(raw, {field: field for field in raw})
    assert errors[0]["field"] == "quantity"


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL required")
def test_worker_chunk_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with TestClient(app) as client:
        token = login(client, create_user(client, "chunk-importer"))
        org_id = create_org(client, token, "chunk-org")
        path = f"/api/v1/organizations/{org_id}/imports"
        rows = [f"P-{i},S-1,2025-01-01,SKU-1,2,10.00,BRL,20.00\n" for i in range(500)]
        uploaded = client.post(
            path,
            headers=csrf_headers(token),
            files={"file": ("chunk.csv", (HEADERS + "".join(rows)).encode())},
        )
        assert uploaded.status_code == 201, uploaded.text
        import_id = uploaded.json()["id"]
        mapping = {field: field for field in HEADERS.strip().split(",")}
        assert (
            client.post(
                f"{path}/{import_id}/confirm",
                headers=csrf_headers(token),
                json={"columns": mapping},
            ).status_code
            == 202
        )
        assert run_once()
        result = client.get(f"{path}/{import_id}").json()
        assert result["status"] == "succeeded"
        assert result["row_count"] == 500
