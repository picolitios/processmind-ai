"""Readiness reflects the active authorization dependency, not the broker."""

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import http as health_http
from app.core.config import settings
from app.identity_app import app as identity_app
from app.main import app as business_app


def test_business_readiness_requires_identity_only_in_remote_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keep the database successful so only the authorization boundary changes.
    monkeypatch.setattr(health_http, "make_engine", MagicMock())
    monkeypatch.setattr(health_http, "identity_ready", lambda: False)
    monkeypatch.setattr(settings, "business_auth_mode", "identity")
    with TestClient(business_app) as client:
        unavailable = client.get("/api/v1/health/ready")
        assert unavailable.status_code == 503
        assert unavailable.json() == {"status": "unavailable"}
        assert client.get("/api/v1/health/live").status_code == 200
        monkeypatch.setattr(health_http, "identity_ready", lambda: True)
        assert client.get("/api/v1/health/ready").status_code == 200
    with TestClient(identity_app) as client:
        assert client.get("/api/v1/health/ready").status_code == 200
    monkeypatch.setattr(settings, "business_auth_mode", "database")
    with TestClient(business_app) as client:
        assert client.get("/api/v1/health/ready").status_code == 200


@pytest.mark.parametrize(
    ("status", "marker", "body", "expected"),
    [
        (200, "identity", '{"status":"ok"}', True),
        (503, "identity", '{"status":"ok"}', False),
        (200, "business", '{"status":"ok"}', False),
        (200, "identity", "not json", False),
        (200, "identity", '{"status":"degraded"}', False),
    ],
)
def test_identity_probe_validates_service_and_body(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    marker: str,
    body: str,
    expected: bool,
) -> None:
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/health/ready"
        assert "Cookie" not in request.headers
        return httpx.Response(status, text=body, headers={"X-ProcessMind-Service": marker})

    def client_factory(*, timeout: float, trust_env: bool) -> httpx.Client:
        assert (timeout, trust_env) == (2, False)
        return original_client(
            transport=httpx.MockTransport(handler), timeout=timeout, trust_env=trust_env
        )

    monkeypatch.setattr(httpx, "Client", client_factory)
    assert health_http.identity_ready() is expected


def test_identity_probe_fails_closed_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("test outage", request=request)

    def client_factory(*, timeout: float, trust_env: bool) -> httpx.Client:
        return original_client(
            transport=httpx.MockTransport(handler), timeout=timeout, trust_env=trust_env
        )

    monkeypatch.setattr(httpx, "Client", client_factory)
    assert health_http.identity_ready() is False
