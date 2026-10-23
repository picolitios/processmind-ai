import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.db.engine import make_engine
from app.features.audit.models import AuditFinding, AuditRun
from app.features.audit_trail.models import BusinessAuditEvent
from app.features.identity.models import AuditEvent, User
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def seed_findings(organization_id: str, user_email: str) -> tuple[str, str]:
    with Session(make_engine()) as db:
        user_id = db.scalar(select(User.id).where(User.email == user_email))
        assert user_id is not None
        run = AuditRun(
            organization_id=uuid.UUID(organization_id),
            requester_id=user_id,
            status="succeeded",
            rule_set_version="1.0.0",
            config_snapshot={},
            import_ids=[],
            idempotency_key=uuid.uuid4().hex,
        )
        db.add(run)
        db.flush()
        ids = []
        for _ in range(2):
            finding = AuditFinding(
                organization_id=uuid.UUID(organization_id),
                run_id=run.id,
                rule_code="DUPLICATE",
                rule_version="1.0.0",
                severity="medium",
                review_state="unreviewed",
                explanation="Compra duplicada",
                fingerprint=uuid.uuid4().hex,
            )
            db.add(finding)
            db.flush()
            ids.append(str(finding.id))
        db.commit()
    return ids[0], ids[1]


def test_direct_review_reason_appears_in_tenant_scoped_activity() -> None:
    with TestClient(app) as owner, TestClient(app) as outsider:
        owner_email = create_user(owner, "activity-owner")
        owner_csrf = login(owner, owner_email)
        login(outsider, create_user(outsider, "activity-outsider"))
        org_id = create_org(owner, owner_csrf, "activity-org")
        finding_id, _ = seed_findings(org_id, owner_email)
        base = f"/api/v1/organizations/{org_id}/findings/{finding_id}"
        profile = owner.patch(
            "/api/v1/auth/profile",
            headers=csrf_headers(owner_csrf),
            json={"display_name": "Ana Revisora"},
        )
        assert profile.status_code == 200
        reviewed = owner.patch(
            base,
            headers=csrf_headers(owner_csrf),
            json={"review_state": "dismissed", "reason": "Pedido autorizado, sem duplicidade"},
        )
        assert reviewed.status_code == 200, reviewed.text
        activity = owner.get(f"{base}/activity")
        assert activity.status_code == 200, activity.text
        event = next(
            item for item in activity.json()["items"] if item["action"] == "finding.reviewed"
        )
        assert event["metadata"]["reason"] == "Pedido autorizado, sem duplicidade"
        assert event["actor_name"] == "Ana Revisora"
        assert outsider.get(f"{base}/activity").status_code == 404


def test_case_lifecycle_review_and_dashboard_isolation() -> None:
    with TestClient(app) as owner, TestClient(app) as outsider, TestClient(app) as viewer:
        owner_email = create_user(owner, "case-owner")
        owner_token = login(owner, owner_email)
        outsider_email = create_user(outsider, "case-outsider")
        outsider_token = login(outsider, outsider_email)
        viewer_email = create_user(viewer, "case-viewer")
        viewer_token = login(viewer, viewer_email)
        org_id = create_org(owner, owner_token, "case-org")
        other_org = create_org(outsider, outsider_token, "other-case-org")
        base = f"/api/v1/organizations/{org_id}"
        assert (
            owner.post(
                f"{base}/users",
                headers=csrf_headers(owner_token),
                json={"email": viewer_email, "role": "viewer"},
            ).status_code
            == 201
        )
        first, second = seed_findings(org_id, owner_email)
        assert outsider.get(f"{base}/cases").status_code == 404
        assert outsider.get(f"{base}/analytics/overview").status_code == 404
        assert (
            owner.post(
                f"{base}/cases",
                headers=csrf_headers(owner_token),
                json={
                    "finding_id": first,
                    "assignee_user_id": outsider.get("/api/v1/auth/session").json()["user"]["id"],
                },
            ).status_code
            == 422
        )
        created = owner.post(
            f"{base}/cases",
            headers=csrf_headers(owner_token),
            json={"finding_id": first},
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["id"]
        assert (
            owner.post(
                f"{base}/cases", headers=csrf_headers(owner_token), json={"finding_id": first}
            ).status_code
            == 409
        )
        assert (
            viewer.post(
                f"{base}/cases", headers=csrf_headers(viewer_token), json={"finding_id": second}
            ).status_code
            == 403
        )
        assert outsider.get(f"{base}/cases/{case_id}").status_code == 404
        assert viewer.get(f"{base}/cases/{case_id}").status_code == 200
        assert owner.get(f"{base}/findings/{first}").json()["review_state"] == "in_review"
        assert (
            owner.patch(
                f"{base}/cases/{case_id}",
                headers=csrf_headers(owner_token),
                json={"status": None},
            ).status_code
            == 422
        )
        assert (
            owner.patch(
                f"{base}/cases/{case_id}",
                headers=csrf_headers(owner_token),
                json={"status": "in_review"},
            ).status_code
            == 200
        )
        assert (
            owner.patch(
                f"{base}/findings/{first}",
                headers=csrf_headers(owner_token),
                json={"review_state": "resolved", "reason": "Conferido"},
            ).status_code
            == 409
        )
        for body in ("Conferir pedido", "Pedido confirmado"):
            comment = owner.post(
                f"{base}/cases/{case_id}/comments",
                headers=csrf_headers(owner_token),
                json={"body": body},
            )
            assert comment.status_code == 201
        page = owner.get(f"{base}/cases/{case_id}/comments", params={"limit": 1}).json()
        assert len(page["items"]) == 1 and page["next_cursor"]
        next_page = owner.get(
            f"{base}/cases/{case_id}/comments", params={"limit": 1, "cursor": page["next_cursor"]}
        ).json()
        assert next_page["items"][0]["id"] != page["items"][0]["id"]
        assert (
            owner.patch(
                f"{base}/cases/{case_id}",
                headers=csrf_headers(owner_token),
                json={"status": "resolved"},
            ).status_code
            == 422
        )
        closed = owner.patch(
            f"{base}/cases/{case_id}",
            headers=csrf_headers(owner_token),
            json={"status": "resolved", "closure_reason": "Pedido válido"},
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["closed_at"]
        assert (
            owner.patch(
                f"{base}/cases/{case_id}",
                headers=csrf_headers(owner_token),
                json={"status": "in_review"},
            ).status_code
            == 409
        )
        assert owner.get(f"{base}/findings/{first}").json()["review_state"] == "resolved"
        detail = owner.get(f"{base}/cases/{case_id}").json()
        assert len(detail["comments"]) == 2
        assert {event["action"] for event in detail["history"]} >= {
            "case.opened",
            "case.status_changed",
        }
        # Both append-only tables must carry the same case events during cutover.
        with Session(make_engine()) as db:
            legacy = db.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == uuid.UUID(org_id),
                    AuditEvent.subject_type == "case",
                    AuditEvent.subject_id == uuid.UUID(case_id),
                )
            ).all()
            owned = db.scalars(
                select(BusinessAuditEvent).where(
                    BusinessAuditEvent.organization_id == uuid.UUID(org_id),
                    BusinessAuditEvent.subject_type == "case",
                    BusinessAuditEvent.subject_id == uuid.UUID(case_id),
                )
            ).all()
            assert len(owned) >= 2
            assert {item.id: (item.action, item.metadata_json) for item in owned} == {
                item.id: (item.action, item.metadata_json) for item in legacy
            }
        assert (
            owner.patch(
                f"{base}/findings/{second}",
                headers=csrf_headers(owner_token),
                json={"review_state": "dismissed"},
            ).status_code
            == 422
        )
        assert (
            owner.patch(
                f"{base}/findings/{second}",
                headers=csrf_headers(owner_token),
                json={"review_state": "dismissed", "reason": "Falso positivo"},
            ).status_code
            == 200
        )
        overview = owner.get(f"{base}/analytics/overview").json()
        assert overview["audits"] >= 1
        assert overview["findings_by_severity"]["medium"] >= 2
        assert overview["pending_cases"] == 0
        assert overview["resolved_cases"] >= 1
        assert overview["categories"] == [] and overview["limitations"]
        assert (
            owner.get(
                f"{base}/analytics/overview", params={"from": "2026-10-15", "to": "2026-10-14"}
            ).status_code
            == 422
        )
        assert outsider.get(f"/api/v1/organizations/{other_org}/cases/{case_id}").status_code == 404
