from unittest.mock import MagicMock, Mock

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.features.ingestion import worker


@pytest.mark.parametrize(
    ("group", "dispatch", "expected"),
    [
        ("import", "broker", ("import",)),
        ("import", "database", ("import",)),
        ("model", "broker", ("ai", "copilot")),
        ("model", "database", ("ai", "copilot")),
        ("auto", "broker", ("import", "ai", "copilot")),
        ("all", "broker", ("import", "ai", "copilot")),
        ("auto", "database", ("import", "audit", "ai", "copilot")),
        ("all", "database", ("import", "audit", "ai", "copilot")),
    ],
)
def test_worker_groups_keep_claims_disjoint_and_rollback_available(
    monkeypatch: pytest.MonkeyPatch, group: str, dispatch: str, expected: tuple[str, ...]
) -> None:
    monkeypatch.setattr(settings, "worker_job_group", group)
    monkeypatch.setattr(settings, "audit_dispatch_mode", dispatch)
    assert worker.allowed_job_types() == expected


def test_invalid_worker_group_fails_configuration() -> None:
    with pytest.raises(ValidationError, match="WORKER_JOB_GROUP"):
        Settings(worker_job_group="other", _env_file=None)


@pytest.mark.parametrize(("group", "purges"), [("import", False), ("model", True)])
def test_temporary_chat_cleanup_runs_only_on_model_worker(
    monkeypatch: pytest.MonkeyPatch, group: str, purges: bool
) -> None:
    monkeypatch.setattr(settings, "worker_job_group", group)
    monkeypatch.setattr(settings, "audit_dispatch_mode", "broker")
    session = MagicMock()
    cleanup = Mock()
    monkeypatch.setattr(worker, "make_engine", Mock())
    monkeypatch.setattr(worker, "Session", lambda _: session)
    monkeypatch.setattr(worker, "claim_job", lambda _: None)
    monkeypatch.setattr(worker, "purge_expired_temporary", cleanup)
    assert worker.run_once() is False
    assert cleanup.called is purges
