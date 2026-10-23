import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.db.engine import make_engine
from app.features.identity.models import OrganizationInvite
from app.identity_app import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def test_invite_requires_email_confirmation_and_preserves_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[EmailMessage] = []
    monkeypatch.setattr(
        "app.features.identity.mail.smtplib.SMTP", lambda *args, **kwargs: Mailbox(delivered)
    )
    monkeypatch.setattr("app.features.identity.mail.settings.smtp_host", "mailpit")
    with TestClient(app) as owner, TestClient(app) as invited, TestClient(app) as outsider:
        owner_email = create_user(owner, "invite-owner")
        invited_email = create_user(invited, "invite-person")
        outsider_email = create_user(outsider, "invite-outsider")
        owner_csrf = login(owner, owner_email)
        invited_csrf = login(invited, invited_email)
        outsider_csrf = login(outsider, outsider_email)
        org_id = create_org(owner, owner_csrf, "invite-org")
        path = f"/api/v1/organizations/{org_id}"
        assert invited.get(path).status_code == 404
        assert (
            outsider.post(
                f"{path}/invitations",
                headers=csrf_headers(outsider_csrf),
                json={"email": invited_email, "role": "analyst"},
            ).status_code
            == 404
        )
        sent = owner.post(
            f"{path}/invitations",
            headers=csrf_headers(owner_csrf),
            json={"email": invited_email, "role": "analyst"},
        )
        assert sent.status_code == 201, sent.text
        assert "token" not in sent.json()
        assert invited.get(path).status_code == 404
        assert len(delivered) == 1
        token = re.search(r"/invite#([\w-]+)", delivered[0].get_content())
        assert token is not None
        secret = token.group(1)
        assert (
            outsider.post(
                "/api/v1/auth/invitations/accept",
                headers=csrf_headers(outsider_csrf),
                json={"token": secret},
            ).status_code
            == 403
        )
        accepted = invited.post(
            "/api/v1/auth/invitations/accept",
            headers=csrf_headers(invited_csrf),
            json={"token": secret},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["role"] == "analyst"
        assert invited.get(path).status_code == 200
        assert invited.get("/api/v1/auth/session").json()["user"]["email_verified"]
        assert (
            invited.post(
                "/api/v1/auth/invitations/accept",
                headers=csrf_headers(invited_csrf),
                json={"token": secret},
            ).status_code
            == 200
        )
        profile = invited.patch(
            "/api/v1/auth/profile",
            headers=csrf_headers(invited_csrf),
            json={"display_name": "Maria Silva"},
        )
        assert profile.status_code == 200
        members = owner.get(f"{path}/users").json()["items"]
        assert any(member["display_name"] == "Maria Silva" for member in members)
        assert outsider.get(f"{path}/invitations").status_code == 404


def test_expired_and_cancelled_invites_cannot_be_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    delivered: list[EmailMessage] = []
    monkeypatch.setattr(
        "app.features.identity.mail.smtplib.SMTP", lambda *args, **kwargs: Mailbox(delivered)
    )
    monkeypatch.setattr("app.features.identity.mail.settings.smtp_host", "mailpit")
    with TestClient(app) as owner, TestClient(app) as invited:
        owner_csrf = login(owner, create_user(owner, "expiry-owner"))
        invited_email = create_user(invited, "expiry-person")
        invited_csrf = login(invited, invited_email)
        org_id = create_org(owner, owner_csrf, "expiry-org")
        base = f"/api/v1/organizations/{org_id}/invitations"
        first = owner.post(
            base, headers=csrf_headers(owner_csrf), json={"email": invited_email, "role": "viewer"}
        )
        assert first.status_code == 201
        token = re.search(r"/invite#([\w-]+)", delivered[-1].get_content())
        assert token is not None
        owner.post(f"{base}/{first.json()['id']}/cancel", headers=csrf_headers(owner_csrf))
        assert (
            invited.post(
                "/api/v1/auth/invitations/accept",
                headers=csrf_headers(invited_csrf),
                json={"token": token.group(1)},
            ).status_code
            == 422
        )
        second = owner.post(
            base, headers=csrf_headers(owner_csrf), json={"email": invited_email, "role": "viewer"}
        )
        assert second.status_code == 201
        token = re.search(r"/invite#([\w-]+)", delivered[-1].get_content())
        assert token is not None
        with Session(make_engine()) as db:
            invite = db.scalar(
                select(OrganizationInvite).where(
                    OrganizationInvite.id == uuid.UUID(second.json()["id"])
                )
            )
            assert invite is not None
            invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        assert (
            invited.post(
                "/api/v1/auth/invitations/accept",
                headers=csrf_headers(invited_csrf),
                json={"token": token.group(1)},
            ).status_code
            == 422
        )


def test_mail_failure_does_not_create_active_or_pending_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.features.identity.mail.settings.smtp_host", "")
    with TestClient(app) as owner:
        owner_csrf = login(owner, create_user(owner, "mail-owner"))
        org_id = create_org(owner, owner_csrf, "mail-org")
        base = f"/api/v1/organizations/{org_id}"
        sent = owner.post(
            f"{base}/invitations", headers=csrf_headers(owner_csrf),
            json={"email": "recipient@example.com", "role": "viewer"},
        )
        assert sent.status_code == 503
        assert owner.get(f"{base}/invitations").json() == []
        assert len(owner.get(f"{base}/users").json()["items"]) == 1


class Mailbox:
    def __init__(self, messages: list[EmailMessage]) -> None:
        self.messages = messages

    def __enter__(self) -> "Mailbox":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)
