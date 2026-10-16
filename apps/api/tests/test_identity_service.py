import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import settings
from app.core.errors import ApiError
from app.features.identity import client as identity_client
from app.features.identity.introspection import IntrospectionResult, signature
from app.identity_app import app as identity_app
from app.main import app as business_app


def test_identity_app_has_only_identity_and_health_routes() -> None:
    with TestClient(identity_app) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/organizations/{organization_id}/users" in paths
        assert "/api/v1/health/ready" in paths
        assert not any("/imports" in path or "/audits" in path for path in paths)
        assert "/internal/v1/session/introspect" not in paths
        assert client.get("/api/v1/health/live").headers["x-processmind-service"] == "identity"


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required")
def test_identity_session_authorizes_business_api_and_preserves_tenant_isolation() -> None:
    with (
        TestClient(identity_app) as identity,
        TestClient(identity_app) as outsider,
        TestClient(business_app) as business,
    ):
        token = login(identity, create_user(identity, "service-owner"))
        other_token = login(outsider, create_user(outsider, "service-outsider"))
        org_id = create_org(identity, token, "service-org")
        other_org_id = create_org(outsider, other_token, "service-other")
        session_cookie = identity.cookies.get("pm_session")
        assert session_cookie is not None
        business.cookies.set("pm_session", session_cookie)

        own = business.get(f"/api/v1/organizations/{org_id}/audits")
        assert own.status_code == 200, own.text
        assert business.get(f"/api/v1/organizations/{other_org_id}/audits").status_code == 404
        assert (
            identity.post(
                f"/api/v1/organizations/{org_id}/users",
                headers=csrf_headers(token),
                json={"email": f"unknown-{uuid.uuid4().hex}@example.com", "role": "viewer"},
            ).status_code
            == 404
        )


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required")
def test_signed_introspection_and_business_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(identity_app) as identity, TestClient(business_app) as business:
        csrf = login(identity, create_user(identity, "introspection-owner"))
        org_id = create_org(identity, csrf, "introspection-org")
        cookie = identity.cookies.get("pm_session")
        assert cookie is not None
        business.cookies.set("pm_session", cookie)
        path = "/internal/v1/session/introspect"
        payload = {"session_token": cookie, "csrf_token": csrf}
        timestamp = str(int(time.time()))

        assert identity.post(path, json=payload).status_code == 422
        assert identity.post(
            path,
            json=payload,
            headers={"X-Internal-Timestamp": timestamp, "X-Internal-Signature": "0" * 64},
        ).status_code == 403
        signed = identity.post(
            path,
            json=payload,
            headers={
                "X-Internal-Timestamp": timestamp,
                "X-Internal-Signature": signature(timestamp, cookie, csrf),
            },
        )
        assert signed.status_code == 200, signed.text
        assert signed.json()["csrf_valid"] is True

        def local_introspection(token: str, csrf_token: str | None = None) -> IntrospectionResult:
            now = str(int(time.time()))
            result = identity.post(
                path,
                json={"session_token": token, "csrf_token": csrf_token},
                headers={
                    "X-Internal-Timestamp": now,
                    "X-Internal-Signature": signature(now, token, csrf_token),
                },
            )
            if result.status_code == 401:
                raise ApiError(401, "unauthorized", "Sessão inválida")
            assert result.status_code == 200, result.text
            return IntrospectionResult.model_validate(result.json())

        monkeypatch.setattr(settings, "business_auth_mode", "identity")
        monkeypatch.setattr(identity_client, "introspect_remote", local_introspection)
        assert business.get(f"/api/v1/organizations/{org_id}/audits").status_code == 200
        create_path = f"/api/v1/organizations/{org_id}/audits"
        body = {"import_ids": [str(uuid.uuid4())]}
        assert business.post(create_path, json=body).status_code == 403
        assert business.post(
            create_path,
            headers=csrf_headers("invalid"),
            json=body,
        ).status_code == 403
        assert business.post(
            create_path,
            headers={**csrf_headers(csrf), "Idempotency-Key": "test-key-123"},
            json=body,
        ).status_code == 422

        def unavailable(token: str, csrf_token: str | None = None) -> IntrospectionResult:
            raise ApiError(503, "identity_unavailable", "Identidade indisponível")

        monkeypatch.setattr(identity_client, "introspect_remote", unavailable)
        assert business.get(f"/api/v1/organizations/{org_id}/audits").status_code == 503
        monkeypatch.setattr(identity_client, "introspect_remote", local_introspection)
        assert identity.post("/api/v1/auth/logout", headers=csrf_headers(csrf)).status_code == 204
        assert business.get(f"/api/v1/organizations/{org_id}/audits").status_code == 401
