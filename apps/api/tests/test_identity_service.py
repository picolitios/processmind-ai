import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import Settings, settings
from app.core.errors import ApiError
from app.features.identity import client as identity_client
from app.features.identity.introspection import (
    IntrospectionResult,
    MembershipResult,
    member_references_subject,
    signature,
)
from app.identity_app import app as identity_app
from app.main import app as business_app
from app.main import create_app


def test_identity_app_has_only_identity_and_health_routes() -> None:
    with TestClient(identity_app) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/organizations/{organization_id}/users" in paths
        assert "/api/v1/health/ready" in paths
        assert not any("/imports" in path or "/audits" in path for path in paths)
        assert "/internal/v1/session/introspect" not in paths
        assert "/internal/v1/membership/authorize" not in paths
        assert "/internal/v1/membership/references" not in paths
        assert client.get("/api/v1/health/live").headers["x-processmind-service"] == "identity"


def test_business_app_omits_identity_routes_in_remote_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "business_auth_mode", "identity")
    paths = create_app().openapi()["paths"]
    assert "/api/v1/auth/login" not in paths
    assert "/api/v1/organizations" not in paths
    assert "/api/v1/organizations/{organization_id}/users" not in paths
    assert "/api/v1/organizations/{organization_id}/audits" in paths


def test_remote_authorization_requires_audit_owned_configuration() -> None:
    with pytest.raises(ValueError, match="AUDIT_CONFIG_MODE must be owned"):
        Settings(
            _env_file=None,
            business_auth_mode="identity",
            audit_config_mode="legacy",
            audit_config_write_mode="database",
        )


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

        def local_membership(token: str, organization_id: uuid.UUID) -> MembershipResult:
            now = str(int(time.time()))
            result = identity.post(
                "/internal/v1/membership/authorize",
                json={"session_token": token, "organization_id": str(organization_id)},
                headers={
                    "X-Internal-Timestamp": now,
                    "X-Internal-Signature": signature(
                        now, token, f"membership:{organization_id}"
                    ),
                },
            )
            if result.status_code == 404:
                raise ApiError(404, "not_found", "Organização não encontrada")
            if result.status_code == 401:
                raise ApiError(401, "unauthorized", "Sessão inválida")
            assert result.status_code == 200, result.text
            return MembershipResult.model_validate(result.json())

        monkeypatch.setattr(identity_client, "authorize_membership_remote", local_membership)
        # A successful private authorization must not trigger a second SQL lookup
        # of the organization's identity-owned row in the business process.
        def unexpected_identity_query(*args: object, **kwargs: object) -> None:
            raise AssertionError("business authorization queried an identity table")

        monkeypatch.setattr(identity_client, "select", unexpected_identity_query)
        assert business.get(f"/api/v1/organizations/{org_id}/audits").status_code == 200
        assert business.get(f"/api/v1/organizations/{uuid.uuid4()}/audits").status_code == 404
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

        def membership_unavailable(token: str, organization_id: uuid.UUID) -> MembershipResult:
            raise ApiError(503, "identity_unavailable", "Identidade indisponível")

        monkeypatch.setattr(identity_client, "authorize_membership_remote", membership_unavailable)
        assert business.get(f"/api/v1/organizations/{org_id}/audits").status_code == 503
        monkeypatch.setattr(identity_client, "authorize_membership_remote", local_membership)
        assert identity.post("/api/v1/auth/logout", headers=csrf_headers(csrf)).status_code == 204
        assert business.get(f"/api/v1/organizations/{org_id}/audits").status_code == 401


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required")
def test_member_references_are_tenant_scoped_and_preserve_inactive_history() -> None:
    with (
        TestClient(identity_app) as owner,
        TestClient(identity_app) as member,
        TestClient(identity_app) as outsider,
    ):
        owner_csrf = login(owner, create_user(owner, "reference-owner"))
        member_email = create_user(member, "reference-member")
        login(member, member_email)
        outsider_csrf = login(outsider, create_user(outsider, "reference-outsider"))
        org_id = create_org(owner, owner_csrf, "reference-org")
        other_org = create_org(outsider, outsider_csrf, "reference-other")
        member_user_id = member.get("/api/v1/auth/session").json()["user"]["id"]
        added = owner.post(
            f"/api/v1/organizations/{org_id}/users",
            headers=csrf_headers(owner_csrf),
            json={"email": member_email, "role": "viewer"},
        )
        assert added.status_code == 201, added.text
        assert added.json()["user_id"] == member_user_id
        cookie = owner.cookies.get("pm_session")
        assert cookie is not None
        path = "/internal/v1/membership/references"
        payload = {
            "session_token": cookie,
            "organization_id": org_id,
            "membership_ids": [],
            "user_id": member_user_id,
        }
        timestamp = str(int(time.time()))
        headers = {
            "X-Internal-Timestamp": timestamp,
            "X-Internal-Signature": signature(
                timestamp,
                cookie,
                member_references_subject(uuid.UUID(org_id), [], uuid.UUID(member_user_id)),
            ),
        }
        assert (
            owner.post(
                path, json=payload, headers={**headers, "X-Internal-Signature": "0" * 64}
            ).status_code
            == 403
        )
        lookup = owner.post(path, json=payload, headers=headers)
        assert lookup.status_code == 200, lookup.text
        assert lookup.json()["members"][0]["user_id"] == member_user_id
        assert lookup.json()["members"][0]["status"] == "active"
        member_id = uuid.UUID(lookup.json()["members"][0]["membership_id"])
        by_id = {**payload, "membership_ids": [str(member_id)], "user_id": None}
        by_id_time = str(int(time.time()))
        by_id_headers = {
            "X-Internal-Timestamp": by_id_time,
            "X-Internal-Signature": signature(
                by_id_time,
                cookie,
                member_references_subject(uuid.UUID(org_id), [member_id], None),
            ),
        }
        by_id_response = owner.post(path, json=by_id, headers=by_id_headers)
        assert by_id_response.status_code == 200
        assert by_id_response.json()["members"][0]["user_id"] == member_user_id

        outsider_cookie = outsider.cookies.get("pm_session")
        outsider_user_id = outsider.get("/api/v1/auth/session").json()["user"]["id"]
        assert outsider_cookie is not None
        outsider_time = str(int(time.time()))
        outsider_lookup = outsider.post(
            path,
            json={
                "session_token": outsider_cookie,
                "organization_id": other_org,
                "membership_ids": [],
                "user_id": outsider_user_id,
            },
            headers={
                "X-Internal-Timestamp": outsider_time,
                "X-Internal-Signature": signature(
                    outsider_time,
                    outsider_cookie,
                    member_references_subject(
                        uuid.UUID(other_org), [], uuid.UUID(outsider_user_id)
                    ),
                ),
            },
        )
        assert outsider_lookup.status_code == 200, outsider_lookup.text
        outsider_member_id = uuid.UUID(outsider_lookup.json()["members"][0]["membership_id"])
        cross_tenant = {**payload, "membership_ids": [str(outsider_member_id)], "user_id": None}
        cross_time = str(int(time.time()))
        cross_headers = {
            "X-Internal-Timestamp": cross_time,
            "X-Internal-Signature": signature(
                cross_time,
                cookie,
                member_references_subject(uuid.UUID(org_id), [outsider_member_id], None),
            ),
        }
        cross_result = owner.post(path, json=cross_tenant, headers=cross_headers)
        assert cross_result.status_code == 200
        assert cross_result.json()["members"] == []

        inactive = owner.patch(
            f"/api/v1/organizations/{org_id}/users/{member_user_id}",
            headers=csrf_headers(owner_csrf),
            json={"status": "inactive"},
        )
        assert inactive.status_code == 200, inactive.text
        historic = owner.post(path, json=payload, headers=headers)
        assert historic.status_code == 200
        assert historic.json()["members"][0]["status"] == "inactive"

        foreign_payload = {**payload, "organization_id": other_org}
        foreign_time = str(int(time.time()))
        foreign_headers = {
            "X-Internal-Timestamp": foreign_time,
            "X-Internal-Signature": signature(
                foreign_time,
                cookie,
                member_references_subject(uuid.UUID(other_org), [], uuid.UUID(member_user_id)),
            ),
        }
        assert owner.post(path, json=foreign_payload, headers=foreign_headers).status_code == 404
