import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.features.audit import monitor
from app.features.audit.broker import DEAD


def clean_snapshot() -> dict[str, object]:
    return {
        "outbox": {"oldest_pending_age_seconds": None},
        "audit_jobs": {"expired_running_leases": 0, "oldest_queued_age_seconds": None},
        "queues": {DEAD: {"ready": 0, "unacknowledged": 0}},
    }


def test_monitor_recovers_from_thresholds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "status.json"
    snapshot = clean_snapshot()
    monkeypatch.setattr(monitor, "collect_snapshot", lambda: snapshot)
    assert not monitor.is_healthy(path)
    assert monitor.sample_once(path)["status"] == "ok"
    assert monitor.is_healthy(path)

    snapshot["queues"][DEAD]["ready"] = 1  # type: ignore[index]
    state = monitor.sample_once(path)
    assert state["status"] == "threshold_exceeded"
    assert state["failures"] == ["audit_dead_letter"]
    assert not monitor.is_healthy(path)

    snapshot["queues"][DEAD]["ready"] = 0  # type: ignore[index]
    assert monitor.sample_once(path)["status"] == "ok"
    assert monitor.is_healthy(path)


def test_unavailable_sample_is_redacted_and_unhealthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "status.json"

    def unavailable() -> None:
        raise RuntimeError("secret tenant=abc prompt=hidden")

    monkeypatch.setattr(monitor, "collect_snapshot", unavailable)
    state = monitor.sample_once(path)
    assert state["status"] == "unavailable"
    assert state["failures"] == ["snapshot_unavailable"]
    assert "secret" not in path.read_text(encoding="utf-8")
    assert "tenant" not in json.dumps(state)
    assert not monitor.is_healthy(path)


def test_stale_and_invalid_state_is_unhealthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "status.json"
    monkeypatch.setattr(settings, "audit_monitor_interval_seconds", 60)
    now = datetime.now(UTC)
    path.write_text(
        json.dumps({"observed_at": (now - timedelta(seconds=151)).isoformat(), "status": "ok"}),
        encoding="utf-8",
    )
    assert not monitor.is_healthy(path, now)
    path.write_text("not-json", encoding="utf-8")
    assert not monitor.is_healthy(path, now)


def test_monitor_configuration_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(audit_monitor_interval_seconds=0, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(audit_monitor_max_pending_age_seconds=-1, _env_file=None)
