"""Local Compose health signal for audit dispatch backlogs and failures."""

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.features.audit.operations import collect_snapshot, threshold_failures

STATUS_PATH = Path("/tmp/processmind-audit-monitor.json")


def sample_once(path: Path = STATUS_PATH) -> dict[str, Any]:
    """Persist a sanitized result atomically, including when a dependency fails."""
    observed_at = datetime.now(UTC).isoformat()
    try:
        snapshot = collect_snapshot()
        failures = threshold_failures(
            snapshot, settings.audit_monitor_max_pending_age_seconds, True, True,
        )
        state = {
            "observed_at": observed_at,
            "status": "threshold_exceeded" if failures else "ok",
            "failures": failures,
        }
    except Exception:
        state = {
            "observed_at": observed_at,
            "status": "unavailable",
            "failures": ["snapshot_unavailable"],
        }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
    return state


def is_healthy(path: Path = STATUS_PATH, now: datetime | None = None) -> bool:
    """Reject failed, missing, invalid or stale samples without exposing details."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        observed_at = datetime.fromisoformat(state["observed_at"])
        age = (now or datetime.now(UTC)) - observed_at
        maximum_age = timedelta(seconds=2 * settings.audit_monitor_interval_seconds + 30)
        return state["status"] == "ok" and timedelta(0) <= age <= maximum_age
    except (OSError, ValueError, KeyError, TypeError):
        return False


def run_forever() -> None:
    """Log state transitions; Docker health reflects the current stored state."""
    previous_state: tuple[str, tuple[str, ...]] | None = None
    while True:
        state = sample_once()
        current_state = (state["status"], tuple(state["failures"]))
        if current_state != previous_state:
            print(json.dumps(state, sort_keys=True), flush=True)
            previous_state = current_state
        time.sleep(settings.audit_monitor_interval_seconds)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        raise SystemExit(0 if is_healthy() else 1)
    if len(sys.argv) == 1:
        run_forever()
    raise SystemExit("usage: python -m app.features.audit.monitor [check]")
