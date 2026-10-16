import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.core.audit_config_contract import ApplyConfiguration
from app.core.config import settings
from app.core.errors import ApiError
from app.core.internal_auth import command_signature
from app.db.engine import make_engine
from app.features.audit.models import AuditConfiguration
from app.features.identity import config_sync
from app.features.identity.models import Organization, OrganizationConfigCommand
from app.identity_app import app as identity_app
from app.main import app as business_app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def apply_through_private_api(
    monkeypatch: pytest.MonkeyPatch, audit_client: TestClient
) -> None:
    """Exercise the signed owner endpoint while keeping tests on an isolated DB."""

    def send(command: OrganizationConfigCommand) -> None:
        payload = ApplyConfiguration(
            command_id=command.id,
            organization_id=command.organization_id,
            settings_version=command.settings_version,
            kind=command.kind,
            amount_limits=command.amount_limits,
            delay_window_days=command.delay_window_days,
        ).model_dump(mode="json")
        timestamp = str(int(time.time()))
        response = audit_client.post(
            "/internal/v1/audit-config/apply",
            json=payload,
            headers={
                "X-Internal-Timestamp": timestamp,
                "X-Internal-Signature": command_signature(timestamp, payload),
            },
        )
        if response.status_code == 409:
            raise config_sync.ConfigurationConflict
        assert response.status_code == 200, response.text

    monkeypatch.setattr(config_sync, "apply_remote", send)


def test_coordinated_creation_and_update_preserve_public_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "audit_config_write_mode", "coordinated")
    with TestClient(business_app) as audit_client, TestClient(identity_app) as identity:
        apply_through_private_api(monkeypatch, audit_client)
        token = login(identity, create_user(identity, "coordinated-owner"))
        org_id = create_org(identity, token, "coordinated-org")
        base = f"/api/v1/organizations/{org_id}"
        original = identity.get(base).json()
        create_replay = identity.post(
            "/api/v1/organizations",
            headers=csrf_headers(token),
            json={"name": original["name"], "slug": original["slug"]},
        )
        assert create_replay.status_code == 201 and create_replay.json()["id"] == org_id
        response = identity.patch(
            base,
            headers=csrf_headers(token),
            json={"amount_limits": {"BRL": "100.00"}, "delay_window_days": 30},
        )
        assert response.status_code == 200, response.text
        assert response.json()["settings_version"] == 2
        assert identity.get(base).json() == response.json()
        assert len(identity.get("/api/v1/organizations").json()) == 1
    with Session(make_engine()) as db:
        org = db.get(Organization, uuid.UUID(org_id))
        config = db.get(AuditConfiguration, uuid.UUID(org_id))
        commands = db.query(OrganizationConfigCommand).filter_by(
            organization_id=uuid.UUID(org_id)
        ).all()
        assert org is not None and org.status == "active"
        assert config is not None
        assert (config.settings_version, config.amount_limits, config.delay_window_days) == (
            2, {"BRL": "100.00"}, 30
        )
        assert [command.status for command in commands] == ["applied", "applied"]


def test_timeout_keeps_pending_command_until_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "audit_config_write_mode", "coordinated")
    with TestClient(business_app) as audit_client, TestClient(identity_app) as identity:
        apply_through_private_api(monkeypatch, audit_client)
        token = login(identity, create_user(identity, "recover-owner"))
        org_id = create_org(identity, token, "recover-org")
        base = f"/api/v1/organizations/{org_id}"
        working_apply = config_sync.apply_remote

        def unavailable(_: OrganizationConfigCommand) -> None:
            raise ApiError(503, "audit_configuration_unavailable", "Configuração indisponível")

        monkeypatch.setattr(config_sync, "apply_remote", unavailable)
        response = identity.patch(
            base, headers=csrf_headers(token), json={"delay_window_days": 45}
        )
        assert response.status_code == 503
        assert identity.get(base).status_code == 503
        assert identity.get("/api/v1/organizations").status_code == 503
        with Session(make_engine()) as db:
            config = db.get(AuditConfiguration, uuid.UUID(org_id))
            assert config is not None and config.settings_version == 1
        monkeypatch.setattr(config_sync, "apply_remote", working_apply)
        assert config_sync.run_once()
        assert identity.get(base).json()["settings_version"] == 2
        replay = identity.patch(
            base, headers=csrf_headers(token), json={"delay_window_days": 45}
        )
        assert replay.status_code == 200 and replay.json()["settings_version"] == 2
        assert config_sync.report() == {"pending": 0, "blocked": 0}


def test_provisioning_is_hidden_and_private_command_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "audit_config_write_mode", "coordinated")
    with TestClient(business_app) as audit_client, TestClient(identity_app) as identity:
        apply_through_private_api(monkeypatch, audit_client)
        token = login(identity, create_user(identity, "pending-owner"))
        working_apply = config_sync.apply_remote

        def unavailable(_: OrganizationConfigCommand) -> None:
            raise ApiError(503, "audit_configuration_unavailable", "Configuração indisponível")

        monkeypatch.setattr(config_sync, "apply_remote", unavailable)
        slug = f"pending-{uuid.uuid4().hex[:10]}"
        response = identity.post(
            "/api/v1/organizations",
            headers=csrf_headers(token),
            json={"name": "Pending", "slug": slug},
        )
        assert response.status_code == 503
        assert identity.get("/api/v1/organizations").json() == []
        with Session(make_engine()) as db:
            org = db.query(Organization).filter_by(slug=slug).one()
            assert org.status == "provisioning"
            org_id = org.id
        monkeypatch.setattr(config_sync, "apply_remote", working_apply)
        retried = identity.post(
            "/api/v1/organizations",
            headers=csrf_headers(token),
            json={"name": "Pending", "slug": slug},
        )
        assert retried.status_code == 201 and retried.json()["id"] == str(org_id)
        assert identity.get(f"/api/v1/organizations/{org_id}").status_code == 200
        with Session(make_engine()) as db:
            command = db.query(OrganizationConfigCommand).filter_by(
                organization_id=org_id
            ).one()
            working_apply(command)  # A timeout after apply can safely repeat the command.
            config = db.get(AuditConfiguration, org_id)
            assert config is not None and config.settings_version == 1
            payload = ApplyConfiguration(
                command_id=command.id,
                organization_id=org_id,
                settings_version=1,
                kind="provision",
                amount_limits={"BRL": "999.00"},
                delay_window_days=90,
            ).model_dump(mode="json")
        timestamp = str(int(time.time()))
        endpoint = "/internal/v1/audit-config/apply"
        assert audit_client.post(
            endpoint,
            json=payload,
            headers={
                "X-Internal-Timestamp": timestamp,
                "X-Internal-Signature": "0" * 64,
            },
        ).status_code == 403
        stale = str(int(timestamp) - 60)
        assert audit_client.post(
            endpoint,
            json=payload,
            headers={
                "X-Internal-Timestamp": stale,
                "X-Internal-Signature": command_signature(stale, payload),
            },
        ).status_code == 403
        assert audit_client.post(
            endpoint,
            json=payload,
            headers={
                "X-Internal-Timestamp": timestamp,
                "X-Internal-Signature": command_signature(timestamp, payload),
            },
        ).status_code == 409
