"""Measure the real import and audit worker against an isolated benchmark database."""

# ruff: noqa: E402

import argparse
import csv
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Self

import psutil
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from generate_synthetic import SIZES, generate

from app.core.config import settings
from app.features.ingestion.worker import run_once
from app.main import app


class MemoryPeak:
    def __init__(self) -> None:
        self.mib = 0.0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self) -> None:
        process = psutil.Process()
        while not self.stop.wait(0.1):
            self.mib = max(self.mib, process.memory_info().rss / 1024**2)

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        self.thread.join()
        self.mib = max(self.mib, psutil.Process().memory_info().rss / 1024**2)


def checked(response: Response) -> dict[str, object]:
    if response.status_code >= 400:
        raise RuntimeError(f"API returned {response.status_code}: {response.text[:300]}")
    return response.json()


def benchmark(client: TestClient, size: int, seed: int, output_dir: Path) -> dict[str, object]:
    csv_path, _ = generate(size, seed, output_dir)
    unique = uuid.uuid4().hex[:12]
    email = f"bench-{unique}@example.com"
    password = f"Benchmark-{uuid.uuid4().hex}-123"
    checked(client.post("/api/v1/auth/register", json={"email": email, "password": password}))
    session = checked(
        client.post("/api/v1/auth/login", json={"email": email, "password": password})
    )
    client.headers["X-CSRF-Token"] = str(session["csrf_token"])
    org = checked(
        client.post("/api/v1/organizations", json={"name": f"Benchmark {size}", "slug": unique})
    )
    base = f"/api/v1/organizations/{org['id']}"

    started = time.perf_counter()
    with csv_path.open("rb") as source:
        batch = checked(
            client.post(f"{base}/imports", files={"file": (csv_path.name, source, "text/csv")})
        )
    upload_seconds = round(time.perf_counter() - started, 3)
    with csv_path.open(encoding="utf-8", newline="") as source:
        headers = next(csv.reader(source))
    checked(
        client.post(
            f"{base}/imports/{batch['id']}/confirm",
            json={"columns": {header: header for header in headers}},
        )
    )
    started = time.perf_counter()
    with MemoryPeak() as import_memory:
        if not run_once():
            raise RuntimeError("Import job was not processed")
    import_seconds = round(time.perf_counter() - started, 3)
    import_result = checked(client.get(f"{base}/imports/{batch['id']}"))
    if import_result["status"] != "succeeded":
        raise RuntimeError(f"Import job status: {import_result['status']}")

    audit = checked(
        client.post(
            f"{base}/audits",
            headers={"Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [batch["id"]]},
        )
    )
    started = time.perf_counter()
    with MemoryPeak() as audit_memory:
        if not run_once():
            raise RuntimeError("Audit job was not processed")
    audit_seconds = round(time.perf_counter() - started, 3)
    audit_result = checked(client.get(f"{base}/audits/{audit['id']}"))
    if audit_result["status"] != "succeeded":
        raise RuntimeError(f"Audit job status: {audit_result['status']}")

    rows = checked(client.get(f"{base}/imports/{batch['id']}/rows", params={"limit": 1}))
    if not rows["next_cursor"]:
        raise RuntimeError("Import rows are not paginated")
    checked(
        client.get(
            f"{base}/imports/{batch['id']}/rows",
            params={"limit": 1, "cursor": rows["next_cursor"]},
        )
    )
    findings = checked(client.get(f"{base}/findings", params={"limit": 1}))
    if findings["next_cursor"]:
        checked(
            client.get(
                f"{base}/findings", params={"limit": 1, "cursor": findings["next_cursor"]}
            )
        )
    return {
        "size": size,
        "seed": seed,
        "file_mib": round(csv_path.stat().st_size / 1024**2, 3),
        "upload_seconds": upload_seconds,
        "import_seconds": import_seconds,
        "audit_seconds": audit_seconds,
        "import_peak_rss_mib": round(import_memory.mib, 1),
        "audit_peak_rss_mib": round(audit_memory.mib, 1),
        "rows": import_result["row_count"],
        "findings": audit_result["finding_count"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, choices=SIZES, default=SIZES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("synthetic-output"))
    args = parser.parse_args()
    database = make_url(settings.database_url).database or ""
    if not database.startswith("processmind_bench_"):
        raise SystemExit("DATABASE_URL must point to a dedicated processmind_bench_* database")
    with TestClient(
        app, base_url=settings.web_origin, headers={"Origin": settings.web_origin}
    ) as client:
        for selected_size in args.sizes:
            result = benchmark(client, selected_size, args.seed, args.output_dir)
            print(json.dumps(result), flush=True)
