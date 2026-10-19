"""The load result remains mathematically defined and contains only aggregates."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from benchmark_distributed import (  # noqa: E402
    Outcome,
    Sample,
    distribution,
    main,
    percentile,
    summarize,
)


def test_percentiles_interpolate_and_report_empty_samples() -> None:
    assert percentile([], 95) is None
    assert percentile([1.0], 99) == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 95) == 4.8
    assert distribution([]) == {"count": 0, "p50": None, "p95": None, "p99": None}


def test_summary_reports_error_rate_without_identifiers() -> None:
    outcomes = [
        Outcome([Sample("audit_poll", 0.5, 200)], 1.2, 2.4, None),
        Outcome([Sample("audit_poll", 0.7, 503)], None, None, "audit_poll_http_503"),
    ]
    result = summarize(outcomes, 4.0)
    assert result["completed"] == 1
    assert result["failed"] == 1
    assert result["workflow_error_rate"] == 0.5
    assert result["http_error_rate"] == 0.5
    assert result["completed_workflows_per_second"] == 0.25
    assert result["http_status_counts"] == {200: 1, 503: 1}
    assert result["error_counts"] == {"audit_poll_http_503": 1}
    assert result["request_latency_seconds"]["audit_poll"]["p50"] == 0.6
    assert result["audit_completion_seconds"]["count"] == 1
    assert "organization_id" not in result


def test_failure_result_has_no_false_successes() -> None:
    result = summarize([Outcome([], None, None, "TimeoutException")], 1.0)
    assert result["completed"] == 0
    assert result["workflow_error_rate"] == 1.0
    assert result["audit_completion_seconds"]["p99"] is None


def test_cli_requires_explicit_local_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROCESSMIND_LOAD_TEST", raising=False)
    monkeypatch.setattr(sys, "argv", ["benchmark_distributed.py"])
    with pytest.raises(SystemExit, match="2"):
        main()
    monkeypatch.setenv("PROCESSMIND_LOAD_TEST", "1")
    monkeypatch.setattr(
        sys, "argv", ["benchmark_distributed.py", "--base-url", "https://example.com"]
    )
    with pytest.raises(SystemExit, match="2"):
        main()
