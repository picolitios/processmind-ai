"""Operational records stay parseable and free of client or tenant content."""

import io
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.observability import current_correlation_id, logger
from app.features.audit.broker import AuditRequested, Payload, log_delivery
from app.features.identity.client import private_headers
from app.features.identity.introspection import signature, verify_internal_signature
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


def test_private_identity_correlation_is_signed_and_logged(log_stream: io.StringIO) -> None:
    from app.core.http import configure_http

    test_app = FastAPI()
    configure_http(test_app, service_name="identity")

    @test_app.post("/internal/test")
    def private_route(request: Request) -> dict[str, str]:
        correlation = uuid.UUID(request.headers["X-Internal-Correlation-ID"])
        verify_internal_signature(
            request.headers["X-Internal-Timestamp"],
            request.headers["X-Internal-Signature"],
            "private-token", "subject", request, correlation,
        )
        return {"status": "ok"}

    correlation = uuid.uuid4()
    context_token = current_correlation_id.set(str(correlation))
    try:
        headers = private_headers(str(int(time.time())), "private-token", "subject")
    finally:
        current_correlation_id.reset(context_token)
    assert headers["X-Internal-Correlation-ID"] == str(correlation)
    assert headers["X-Internal-Signature"] == signature(
        headers["X-Internal-Timestamp"], "private-token", "subject", correlation
    )
    with TestClient(test_app) as client:
        valid = client.post("/internal/test", headers=headers)
        tampered = client.post(
            "/internal/test", headers={**headers, "X-Internal-Correlation-ID": str(uuid.uuid4())}
        )
    assert valid.status_code == 200
    assert valid.headers["X-Correlation-ID"] == str(correlation)
    assert tampered.status_code == 403
    assert tampered.headers["X-Correlation-ID"] != str(correlation)
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert records[0]["correlation_id"] == str(correlation)
    assert records[1]["correlation_id"] == tampered.headers["X-Correlation-ID"]


def test_browser_cannot_choose_correlation_and_context_does_not_leak() -> None:
    forged = str(uuid.uuid4())
    with TestClient(business_app) as client:
        first = client.get("/api/v1/health/live", headers={"X-Internal-Correlation-ID": forged})
        second = client.get("/api/v1/health/live")
    assert first.headers["X-Correlation-ID"] != forged
    assert second.headers["X-Correlation-ID"] != first.headers["X-Correlation-ID"]
    assert "X-Internal-Correlation-ID" not in private_headers("1", "token", None)
    assert private_headers("1", "token", None)["X-Internal-Signature"] == signature(
        "1", "token", None
    )


def test_sync_business_route_uses_its_own_correlation_context() -> None:
    from app.core.http import configure_http

    test_app = FastAPI()
    configure_http(test_app)

    @test_app.get("/private-headers")
    def read_private_headers() -> dict[str, str]:
        return private_headers("1", "token", None)

    with TestClient(test_app) as client:
        first = client.get("/private-headers")
        second = client.get("/private-headers")
    assert first.json()["X-Internal-Correlation-ID"] == first.headers["X-Correlation-ID"]
    assert second.json()["X-Internal-Correlation-ID"] == second.headers["X-Correlation-ID"]
    assert first.headers["X-Correlation-ID"] != second.headers["X-Correlation-ID"]
