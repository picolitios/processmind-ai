import io
import json
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock

import pytest

from app.features.audit import operations
from app.features.audit.broker import DEAD


def test_queue_snapshot_is_aggregate_and_does_not_expose_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> io.BytesIO:
        assert timeout == 5
        urls.append(request.full_url)  # type: ignore[attr-defined]
        assert request.get_header("Authorization").startswith("Basic ")  # type: ignore[attr-defined]
        return io.BytesIO(b'{"messages_ready": 2, "messages_unacknowledged": 1}')

    monkeypatch.setattr(operations, "urlopen", fake_urlopen)
    snapshot = operations.queue_metrics()
    assert len(urls) == len(operations.QUEUES)
    assert snapshot[DEAD] == {"ready": 2, "unacknowledged": 1}
    assert operations.settings.rabbitmq_password not in json.dumps(snapshot)


def test_thresholds_only_report_configured_conditions() -> None:
    snapshot = {
        "outbox": {"oldest_pending_age_seconds": 61.0},
        "audit_jobs": {"expired_running_leases": 1},
        "queues": {DEAD: {"ready": 1, "unacknowledged": 0}},
    }
    assert operations.threshold_failures(snapshot, None, False, False) == []
    assert operations.threshold_failures(snapshot, 60, True, True) == [
        "outbox_pending_age", "audit_expired_lease", "audit_dead_letter"
    ]
    snapshot["outbox"]["oldest_pending_age_seconds"] = None
    assert operations.threshold_failures(snapshot, 60, False, False) == []


def test_main_reports_unavailable_broker_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = Mock()
    session = MagicMock()
    monkeypatch.setattr(operations, "make_engine", lambda: engine)
    monkeypatch.setattr(operations, "Session", lambda _: session)
    monkeypatch.setattr(
        operations, "database_metrics", lambda *_: {"outbox": {}, "audit_jobs": {}}
    )
    monkeypatch.setattr(
        operations, "queue_metrics", lambda: (_ for _ in ()).throw(ConnectionError("secret"))
    )
    monkeypatch.setattr(sys, "argv", ["audit-operations"])
    assert operations.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ConnectionError" in captured.err
    assert "secret" not in captured.err


def test_empty_database_metrics_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    db = Mock()
    db.execute.side_effect = [
        Mock(one=lambda: (0, None)),
        Mock(one=lambda: (0, None, None)),
        Mock(all=lambda: []),
    ]
    db.scalar.return_value = 0
    metrics = operations.database_metrics(db, now)
    assert metrics["outbox"] == {
        "pending": 0,
        "oldest_pending_age_seconds": None,
        "published_24h": 0,
        "publish_latency_mean_seconds": None,
        "publish_latency_p95_seconds": None,
    }
    assert metrics["audit_jobs"] == {"by_status": {}, "expired_running_leases": 0}
