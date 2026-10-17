"""Operational records stay parseable and free of client or tenant content."""

import io
import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.observability import logger
from app.features.audit.broker import AuditRequested, Payload, log_delivery
from app.identity_app import app as identity_app
from app.main import app as business_app


@pytest.fixture
def log_stream(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Capture the dedicated JSON handler without changing application behavior."""
    stream = io.StringIO()
    monkeypatch.setattr(logger.handlers[0], "stream", stream)
    return stream


@pytest.mark.parametrize("app,service", [(business_app, "business"), (identity_app, "identity")])
def test_http_record_uses_route_template_and_response_correlation(
    app: FastAPI, service: str, log_stream: io.StringIO,
) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live?private=must-not-appear")
    assert response.status_code == 200
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    request_record = next(row for row in records if row["action"] == "http_request")
    assert request_record["service"] == service
    assert request_record["correlation_id"] == response.headers["X-Correlation-ID"]
    assert request_record["route"] == "/api/v1/health/live"
    assert request_record["method"] == "GET"
    assert request_record["status_code"] == 200
    assert request_record["duration_ms"] >= 0
    assert "must-not-appear" not in log_stream.getvalue()


def test_audit_record_omits_tenant_and_payload(log_stream: io.StringIO) -> None:
    tenant_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    event_id = uuid.uuid4()
    event = AuditRequested(
        event_id=event_id,
        event_type="audit.requested",
        event_version=1,
        occurred_at=datetime.now(UTC),
        correlation_id=correlation_id,
        causation_id=None,
        tenant_id=tenant_id,
        payload=Payload(audit_id=uuid.uuid4(), job_id=uuid.uuid4()),
    )
    log_delivery(event, "retry", "RuntimeError")
    serialized = log_stream.getvalue()
    record = json.loads(serialized)
    assert record["correlation_id"] == str(correlation_id)
    assert record["event_id"] == str(event_id)
    assert record["outcome"] == "retry"
    assert record["error_type"] == "RuntimeError"
    assert str(tenant_id) not in serialized
    assert str(event.payload.audit_id) not in serialized
    assert str(event.payload.job_id) not in serialized


def test_dynamic_route_does_not_log_path_parameters(log_stream: io.StringIO) -> None:
    from app.core.http import configure_http

    test_app = FastAPI()
    configure_http(test_app)

    @test_app.get("/items/{item_id}")
    def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    with TestClient(test_app) as client:
        response = client.get("/items/private-identifier?token=private-token")
    record = json.loads(log_stream.getvalue())
    assert response.status_code == 200
    assert record["route"] == "/items/{item_id}"
    assert "private-identifier" not in log_stream.getvalue()
    assert "private-token" not in log_stream.getvalue()
