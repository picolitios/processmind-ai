import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, login

from app.db.engine import make_engine
from app.features.identity.models import Membership, User
from app.identity_app import app as identity_app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def test_business_references_are_detached_but_business_fks_remain() -> None:
    with Session(make_engine()) as db:
        links = set(
            db.execute(
                text(
                    "SELECT conrelid::regclass::text, confrelid::regclass::text "
                    "FROM pg_constraint WHERE contype = 'f'"
                )
            ).all()
        )
    identity = {"organizations", "users", "organization_memberships"}
    business = {
        "import_batches",
        "jobs",
        "suppliers",
        "audit_runs",
        "ai_analyses",
        "audit_cases",
        "case_comments",
        "outbox_events",
    }
    assert not {
        (source, target) for source, target in links if source in business and target in identity
    }
    assert ("audit_cases", "audit_findings") in links
    assert ("case_comments", "audit_cases") in links
    assert ("purchases", "import_batches") in links


def test_physical_identity_delete_is_blocked_during_cutover() -> None:
    with TestClient(identity_app) as client:
        email = create_user(client, "fk-delete-owner")
        csrf = login(client, email)
        org_id = uuid.UUID(create_org(client, csrf, "fk-delete-org"))

    with Session(make_engine()) as db:
        user_id = db.scalar(select(User.id).where(User.email == email))
        membership_id = db.scalar(
            select(Membership.id).where(
                Membership.organization_id == org_id, Membership.user_id == user_id
            )
        )
        assert user_id is not None and membership_id is not None
        for table, item_id in (
            ("organizations", org_id),
            ("users", user_id),
            ("organization_memberships", membership_id),
        ):
            with pytest.raises(DBAPIError, match="physical identity deletion is disabled"):
                db.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": item_id})
            db.rollback()
            with pytest.raises(DBAPIError, match="physical identity deletion is disabled"):
                db.execute(text(f"TRUNCATE {table} CASCADE"))
            db.rollback()
