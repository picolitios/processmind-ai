import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.engine import make_engine
from app.features.identity.models import UserSession
from app.features.identity.security import digest
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def create_user(client: TestClient, name: str) -> str:
    email = f"{name}-{uuid.uuid4().hex}@example.com"
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "strong-test-passphrase"}
    )
    assert response.status_code == 201, response.text
    return email


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "strong-test-passphrase"}
    )
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    return str(response.json()["csrf_token"])


def csrf_headers(token: str, origin: str = "http://localhost:5173") -> dict[str, str]:
    return {"X-CSRF-Token": token, "Origin": origin}


def create_org(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/v1/organizations",
        headers=csrf_headers(token),
        json={"name": name, "slug": f"{name}-{uuid.uuid4().hex[:10]}"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_sessions_csrf_roles_and_tenant_isolation() -> None:
    with TestClient(app) as owner_a, TestClient(app) as owner_b, TestClient(app) as viewer:
        email_a = create_user(owner_a, "owner-a")
        email_b = create_user(owner_b, "owner-b")
        viewer_email = create_user(viewer, "viewer")
        token_a = login(owner_a, email_a)
        token_b = login(owner_b, email_b)
        viewer_token = login(viewer, viewer_email)

        assert (
            owner_a.post(
                "/api/v1/organizations", json={"name": "No CSRF", "slug": "no-csrf"}
            ).status_code
            == 403
        )
        assert (
            owner_a.post(
                "/api/v1/organizations",
                headers=csrf_headers(token_a, "https://evil.example"),
                json={"name": "Bad Origin", "slug": "bad-origin"},
            ).status_code
            == 403
        )

        org_a = create_org(owner_a, token_a, "tenant-a")
        org_b = create_org(owner_b, token_b, "tenant-b")
        assert owner_a.get(f"/api/v1/organizations/{org_b}").status_code == 404
        assert owner_b.get(f"/api/v1/organizations/{org_a}/users").status_code == 404
        assert [item["id"] for item in owner_a.get("/api/v1/organizations").json()] == [org_a]

        added = owner_a.post(
            f"/api/v1/organizations/{org_a}/users",
            headers=csrf_headers(token_a),
            json={"email": viewer_email, "role": "viewer"},
        )
        assert added.status_code == 201, added.text
        viewer_id = added.json()["user_id"]
        assert (
            owner_b.patch(
                f"/api/v1/organizations/{org_a}/users/{viewer_id}",
                headers=csrf_headers(token_b),
                json={"role": "admin"},
            ).status_code
            == 404
        )
        assert viewer.get(f"/api/v1/organizations/{org_a}").status_code == 200
        assert viewer.get(f"/api/v1/organizations/{org_a}/users").status_code == 403
        assert (
            viewer.patch(
                f"/api/v1/organizations/{org_a}",
                headers=csrf_headers(viewer_token),
                json={"delay_window_days": 30},
            ).status_code
            == 403
        )
        assert owner_a.patch(
            f"/api/v1/organizations/{org_a}",
            headers=csrf_headers(token_a),
            json={"amount_limits": {"BRL": "1000.00"}},
        ).json()["settings"]["amount_limits"] == {"BRL": "1000.00"}

        changed = owner_a.patch(
            f"/api/v1/organizations/{org_a}/users/{viewer_id}",
            headers=csrf_headers(token_a),
            json={"role": "analyst"},
        )
        assert changed.status_code == 200, changed.text
        assert viewer.get("/api/v1/auth/session").status_code == 401
        viewer_token = login(viewer, viewer_email)
        assert viewer.get(f"/api/v1/organizations/{org_b}").status_code == 404
        assert (
            viewer.post("/api/v1/auth/logout", headers=csrf_headers(viewer_token)).status_code
            == 204
        )
        assert viewer.get("/api/v1/auth/session").status_code == 401


def test_last_owner_and_login_limit() -> None:
    with TestClient(app) as client:
        email = create_user(client, "owner")
        token = login(client, email)
        org_id = create_org(client, token, "protected-owner")
        user_id = client.get("/api/v1/auth/session").json()["user"]["id"]
        response = client.patch(
            f"/api/v1/organizations/{org_id}/users/{user_id}",
            headers=csrf_headers(token),
            json={"status": "inactive"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "last_owner"

        unknown_email = f"unknown-{uuid.uuid4().hex}@example.com"
        for _ in range(5):
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={"email": unknown_email, "password": "wrong-password"},
                ).status_code
                == 401
            )
        limited = client.post(
            "/api/v1/auth/login", json={"email": unknown_email, "password": "wrong-password"}
        )
        assert limited.status_code == 429
        assert limited.json()["code"] == "login_rate_limited"


def test_session_token_is_hashed_and_rotated() -> None:
    with TestClient(app) as client:
        email = create_user(client, "rotation")
        login(client, email)
        old_token = client.cookies.get("pm_session")
        assert old_token is not None
        with Session(make_engine()) as db:
            stored = db.scalar(
                select(UserSession).where(UserSession.token_hash == digest(old_token))
            )
            assert stored is not None
            assert stored.token_hash != old_token
        login(client, email)
        with TestClient(app) as old_client:
            old_client.cookies.set("pm_session", old_token)
            assert old_client.get("/api/v1/auth/session").status_code == 401
