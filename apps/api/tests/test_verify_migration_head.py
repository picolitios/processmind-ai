"""The migration gate compares exact revision sets and never upgrades."""

import json

import pytest

from app.db import verify_migration_head as gate


@pytest.mark.parametrize(
    ("current", "expected", "exit_code"),
    [
        ({"a"}, {"a"}, 0),
        (set(), {"a"}, 2),
        ({"a"}, {"b"}, 2),
        ({"a", "b"}, {"a"}, 2),
    ],
)
def test_revision_gate_requires_exact_heads(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    current: set[str],
    expected: set[str],
    exit_code: int,
) -> None:
    monkeypatch.setattr(gate, "revision_state", lambda: (current, expected))
    assert gate.main() == exit_code
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == ("ok" if exit_code == 0 else "mismatch")


def test_revision_gate_handles_database_failure_without_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable() -> tuple[set[str], set[str]]:
        raise ValueError("postgresql://secret")

    monkeypatch.setattr(gate, "revision_state", unavailable)
    assert gate.main() == 1
    assert capsys.readouterr().out.strip() == '{"status": "unavailable"}'
