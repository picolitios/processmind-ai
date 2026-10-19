"""Measure concurrent synthetic import/audit workflows through the public HTTP edge."""

import argparse
import csv
import json
import os
import tempfile
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from generate_synthetic import SIZES, generate


@dataclass(frozen=True)
class Sample:
    operation: str
    seconds: float
    status_code: int


@dataclass(frozen=True)
class Outcome:
    samples: list[Sample]
    import_seconds: float | None
    audit_seconds: float | None
    error: str | None


class WorkflowFailure(Exception):
    """A stable failure code that cannot include response or tenant data."""


def percentile(values: list[float], percent: int) -> float | None:
    """Interpolate sorted observations without inventing values for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    fraction = position - lower
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + fraction * (ordered[upper] - ordered[lower]), 3)


def distribution(values: list[float]) -> dict[str, float | int | None]:
    """Report the sample size alongside percentile estimates."""
    return {
        "count": len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def summarize(outcomes: list[Outcome], elapsed_seconds: float) -> dict[str, object]:
    """Aggregate only operation/status/timing data; never return workflow identities."""
    samples = [sample for outcome in outcomes for sample in outcome.samples]
    operations = sorted({sample.operation for sample in samples})
    successes = sum(outcome.error is None for outcome in outcomes)
    return {
        "workflows": len(outcomes),
        "completed": successes,
        "failed": len(outcomes) - successes,
        "workflow_error_rate": round((len(outcomes) - successes) / len(outcomes), 4)
        if outcomes
        else None,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "completed_workflows_per_second": round(successes / elapsed_seconds, 3)
        if elapsed_seconds > 0
        else None,
        "request_count": len(samples),
        "http_error_rate": round(
            sum(sample.status_code >= 400 for sample in samples) / len(samples), 4
        )
        if samples
        else None,
        "http_status_counts": dict(
            sorted(Counter(sample.status_code for sample in samples).items())
        ),
        "request_latency_seconds": {
            name: distribution(
                [sample.seconds for sample in samples if sample.operation == name]
            )
            for name in operations
        },
        "import_completion_seconds": distribution(
            [
                outcome.import_seconds
                for outcome in outcomes
                if outcome.import_seconds is not None
            ]
        ),
        "audit_completion_seconds": distribution(
            [
                outcome.audit_seconds
                for outcome in outcomes
                if outcome.audit_seconds is not None
            ]
        ),
        "error_counts": dict(
            sorted(
                Counter(
                    outcome.error for outcome in outcomes if outcome.error is not None
                ).items()
            )
        ),
    }


def request(
    client: httpx.Client,
    samples: list[Sample],
    operation: str,
    method: str,
    path: str,
    expected: int,
    json_body: dict[str, object] | None = None,
    file_upload: tuple[str, bytes, str] | None = None,
    extra_headers: dict[str, str] | None = None,
    params: dict[str, str | int] | None = None,
) -> dict[str, object]:
    """Call one endpoint and retain only its status and elapsed time in results."""
    started = time.perf_counter()
    response = client.request(
        method,
        path,
        json=json_body,
        files={"file": file_upload} if file_upload else None,
        headers=extra_headers,
        params=params,
    )
    samples.append(
        Sample(operation, time.perf_counter() - started, response.status_code)
    )
    if response.status_code != expected:
        raise WorkflowFailure(f"{operation}_http_{response.status_code}")
    result = response.json()
    if not isinstance(result, dict):
        raise WorkflowFailure(f"{operation}_invalid_response")
    return result


def await_job(
    client: httpx.Client,
    samples: list[Sample],
    operation: str,
    path: str,
    deadline: float,
) -> float:
    """Poll the public status contract until success, failure or a bounded timeout."""
    started = time.perf_counter()
    while time.perf_counter() - started < deadline:
        result = request(client, samples, operation, "GET", path, 200)
        if result.get("status") == "succeeded":
            return time.perf_counter() - started
        if result.get("status") == "failed":
            raise WorkflowFailure(f"{operation}_failed")
        time.sleep(0.5)
    raise WorkflowFailure(f"{operation}_timeout")


def workflow(
    base_url: str, csv_bytes: bytes, headers: list[str], deadline: float
) -> Outcome:
    """Run one tenant-isolated journey with a private session and synthetic data."""
    samples: list[Sample] = []
    import_seconds: float | None = None
    audit_seconds: float | None = None
    unique = uuid.uuid4().hex
    try:
        with httpx.Client(
            base_url=base_url, headers={"Origin": base_url}, timeout=30, trust_env=False
        ) as client:
            password = f"Test-{uuid.uuid4().hex}-passphrase"
            request(
                client,
                samples,
                "register",
                "POST",
                "/api/v1/auth/register",
                201,
                json_body={"email": f"load-{unique}@example.com", "password": password},
            )
            login = request(
                client,
                samples,
                "login",
                "POST",
                "/api/v1/auth/login",
                200,
                json_body={"email": f"load-{unique}@example.com", "password": password},
            )
            client.headers["X-CSRF-Token"] = str(login["csrf_token"])
            organization = request(
                client,
                samples,
                "organization",
                "POST",
                "/api/v1/organizations",
                201,
                json_body={"name": "Synthetic load", "slug": f"load-{unique}"},
            )
            prefix = f"/api/v1/organizations/{organization['id']}"
            batch = request(
                client,
                samples,
                "upload",
                "POST",
                f"{prefix}/imports",
                201,
                file_upload=("synthetic.csv", csv_bytes, "text/csv"),
            )
            request(
                client,
                samples,
                "confirm",
                "POST",
                f"{prefix}/imports/{batch['id']}/confirm",
                202,
                json_body={"columns": {header: header for header in headers}},
            )
            import_seconds = await_job(
                client,
                samples,
                "import_poll",
                f"{prefix}/imports/{batch['id']}",
                deadline,
            )
            audit = request(
                client,
                samples,
                "audit_create",
                "POST",
                f"{prefix}/audits",
                202,
                extra_headers={"Idempotency-Key": uuid.uuid4().hex},
                json_body={"import_ids": [batch["id"]]},
            )
            audit_seconds = await_job(
                client,
                samples,
                "audit_poll",
                f"{prefix}/audits/{audit['id']}",
                deadline,
            )
            request(
                client,
                samples,
                "findings",
                "GET",
                f"{prefix}/findings",
                200,
                params={"audit_id": str(audit["id"]), "limit": 1},
            )
        return Outcome(samples, import_seconds, audit_seconds, None)
    except (httpx.HTTPError, KeyError, ValueError, WorkflowFailure) as exc:
        code = str(exc) if isinstance(exc, WorkflowFailure) else type(exc).__name__
        return Outcome(samples, import_seconds, audit_seconds, code)


def main() -> int:
    """Guard the target, execute bounded concurrency and write aggregate evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5173")
    parser.add_argument("--size", type=int, choices=SIZES, default=1000)
    parser.add_argument("--users", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--job-deadline-seconds", type=float, default=180)
    parser.add_argument(
        "--output", type=Path, default=Path("distributed-load-result.json")
    )
    args = parser.parse_args()
    target = urlparse(args.base_url)
    if (
        os.getenv("PROCESSMIND_LOAD_TEST") != "1"
        or target.scheme not in {"http", "https"}
        or target.hostname not in {"localhost", "127.0.0.1"}
        or target.username is not None
        or target.password is not None
        or target.path not in {"", "/"}
        or target.query
        or target.fragment
    ):
        parser.error("requires PROCESSMIND_LOAD_TEST=1 and a loopback URL")
    if not 1 <= args.users <= 8 or not 1 <= args.rounds <= 10:
        parser.error("users must be 1..8 and rounds must be 1..10")
    if not 30 <= args.job_deadline_seconds <= 900:
        parser.error("job deadline must be 30..900 seconds")
    base_url = f"{target.scheme}://{target.netloc}"
    with tempfile.TemporaryDirectory(prefix="processmind-load-") as directory:
        csv_path, _ = generate(args.size, 42, Path(directory))
        csv_bytes = csv_path.read_bytes()
        with csv_path.open(encoding="utf-8", newline="") as source:
            headers = next(csv.reader(source))
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.users) as executor:
            outcomes = list(
                executor.map(
                    lambda _: workflow(
                        base_url, csv_bytes, headers, args.job_deadline_seconds
                    ),
                    range(args.users * args.rounds),
                )
            )
        result = summarize(outcomes, time.perf_counter() - started)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
