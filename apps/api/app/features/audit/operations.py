"""Read-only operational snapshot of the audit event path."""

import argparse
import base64
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.engine import make_engine
from app.features.audit.broker import DEAD, QUEUE, RETRY_5, RETRY_15
from app.features.audit.outbox import OutboxEvent
from app.features.ingestion.models import Job

QUEUES = (QUEUE, RETRY_5, RETRY_15, DEAD)


def database_metrics(db: Session, now: datetime) -> dict[str, Any]:
    """Aggregate the business-owned outbox and audit jobs without reading payloads."""
    pending_count, oldest = db.execute(
        select(func.count(), func.min(OutboxEvent.created_at)).where(
            OutboxEvent.published_at.is_(None)
        )
    ).one()
    latency = func.extract("epoch", OutboxEvent.published_at - OutboxEvent.created_at)
    published_count, mean_latency, p95_latency = db.execute(
        select(
            func.count(),
            func.avg(latency),
            func.percentile_cont(0.95).within_group(latency),
        ).where(OutboxEvent.published_at >= now - timedelta(hours=24))
    ).one()
    job_rows = db.execute(
        select(Job.status, func.count())
        .where(Job.type == "audit")
        .group_by(Job.status)
    ).all()
    expired_leases = db.scalar(
        select(func.count()).select_from(Job).where(
            Job.type == "audit", Job.status == "running", Job.lease_until < now
        )
    )
    oldest_queued = db.scalar(
        select(func.min(Job.created_at)).where(Job.type == "audit", Job.status == "queued")
    )
    return {
        "outbox": {
            "pending": pending_count,
            "oldest_pending_age_seconds": max(0.0, (now - oldest).total_seconds())
            if oldest is not None
            else None,
            "published_24h": published_count,
            "publish_latency_mean_seconds": float(str(mean_latency))
            if mean_latency is not None
            else None,
            "publish_latency_p95_seconds": float(str(p95_latency))
            if p95_latency is not None
            else None,
        },
        "audit_jobs": {
            "by_status": {status: count for status, count in job_rows},
            "expired_running_leases": expired_leases,
            "oldest_queued_age_seconds": max(0.0, (now - oldest_queued).total_seconds())
            if oldest_queued is not None
            else None,
        },
    }


def queue_metrics() -> dict[str, dict[str, int]]:
    """Read queue counters using operator credentials, never including them in output."""
    credentials = base64.b64encode(
        f"{settings.rabbitmq_user}:{settings.rabbitmq_password}".encode()
    ).decode("ascii")
    result: dict[str, dict[str, int]] = {}
    for name in QUEUES:
        base_url = settings.rabbitmq_management_url.rstrip("/")
        url = f"{base_url}/api/queues/%2F/{quote(name, safe='')}"
        request = Request(url, headers={"Authorization": f"Basic {credentials}"})
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        ready = payload["messages_ready"]
        unacknowledged = payload["messages_unacknowledged"]
        if not isinstance(ready, int) or not isinstance(unacknowledged, int):
            raise ValueError("Invalid RabbitMQ queue counters")
        result[name] = {"ready": ready, "unacknowledged": unacknowledged}
    return result


def threshold_failures(
    snapshot: dict[str, Any], max_pending_age_seconds: float | None,
    fail_on_expired_leases: bool, fail_on_dead_letter: bool,
) -> list[str]:
    """Return stable alert names without exposing event or tenant details."""
    failures = []
    age = snapshot["outbox"]["oldest_pending_age_seconds"]
    if max_pending_age_seconds is not None and age is not None and age > max_pending_age_seconds:
        failures.append("outbox_pending_age")
    queued_age = snapshot["audit_jobs"]["oldest_queued_age_seconds"]
    if (
        max_pending_age_seconds is not None
        and queued_age is not None
        and queued_age > max_pending_age_seconds
    ):
        failures.append("audit_queued_age")
    if fail_on_expired_leases and snapshot["audit_jobs"]["expired_running_leases"] > 0:
        failures.append("audit_expired_lease")
    if fail_on_dead_letter and sum(snapshot["queues"][DEAD].values()) > 0:
        failures.append("audit_dead_letter")
    return failures


def collect_snapshot() -> dict[str, Any]:
    """Collect one read-only observation for CLI or local Compose monitoring."""
    now = datetime.now(UTC)
    with Session(make_engine()) as db:
        snapshot = {"observed_at": now.isoformat(), **database_metrics(db, now)}
    snapshot["queues"] = queue_metrics()
    return snapshot


def main() -> int:
    """Print one machine-readable observation and signal unavailable or stale paths."""
    parser = argparse.ArgumentParser(description="Inspect audit dispatch without modifying data")
    parser.add_argument("--max-pending-age-seconds", type=float)
    parser.add_argument("--fail-on-expired-leases", action="store_true")
    parser.add_argument("--fail-on-dead-letter", action="store_true")
    args = parser.parse_args()
    if args.max_pending_age_seconds is not None and args.max_pending_age_seconds < 0:
        parser.error("--max-pending-age-seconds must be nonnegative")
    try:
        snapshot = collect_snapshot()
        failures = threshold_failures(
            snapshot, args.max_pending_age_seconds,
            args.fail_on_expired_leases, args.fail_on_dead_letter,
        )
        snapshot["status"] = "threshold_exceeded" if failures else "ok"
        snapshot["failures"] = failures
        print(json.dumps(snapshot, sort_keys=True))
        return 2 if failures else 0
    except Exception as exc:
        print(f"Audit operation snapshot unavailable ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
