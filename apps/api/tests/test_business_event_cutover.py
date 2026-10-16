import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, login

from app.core.config import settings
from app.db.engine import make_engine
from app.db.reconcile_business_events import collect_report, restore_legacy_copy
from app.features.audit_trail.events import append_business_event
from app.features.audit_trail.models import BusinessAuditEvent
from app.features.identity.models import AuditEvent
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def test_owned_events_can_be_reconciled_for_legacy_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        token = login(client, create_user(client, "event-cutover"))
        organization_id = uuid.UUID(create_org(client, token, "event-cutover-org"))

    with make_engine().connect() as connection:
        transaction = connection.begin()
        try:
            baseline = collect_report(connection)
            assert baseline["status"] == "clean"
            monkeypatch.setattr(settings, "business_event_write_mode", "owned")
            with Session(bind=connection) as db:
                subject_id = uuid.uuid4()
                append_business_event(
                    db, organization_id, None, "case.test_cutover", "case", subject_id
                )
                db.flush()
            owned_id = connection.scalar(
                select(BusinessAuditEvent.id).where(
                    BusinessAuditEvent.organization_id == organization_id,
                    BusinessAuditEvent.subject_id == subject_id,
                )
            )
            assert owned_id is not None
            assert connection.scalar(
                select(AuditEvent.id).where(AuditEvent.id == owned_id)
            ) is None
            report = collect_report(connection)
            assert report["owned_only"] == baseline["owned_only"] + 1
            assert restore_legacy_copy(connection) == int(report["owned_only"])
            assert collect_report(connection)["owned_only"] == 0
            assert restore_legacy_copy(connection) == 0
            assert connection.scalar(
                select(AuditEvent.id).where(AuditEvent.id == owned_id)
            ) == owned_id
        finally:
            transaction.rollback()


def test_dual_mode_keeps_atomic_legacy_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        token = login(client, create_user(client, "event-dual"))
        organization_id = uuid.UUID(create_org(client, token, "event-dual-org"))

    monkeypatch.setattr(settings, "business_event_write_mode", "dual")
    with make_engine().connect() as connection:
        transaction = connection.begin()
        try:
            subject_id = uuid.uuid4()
            with Session(bind=connection) as db:
                append_business_event(
                    db, organization_id, None, "case.test_dual", "case", subject_id
                )
                db.flush()
            owned_id = connection.scalar(
                select(BusinessAuditEvent.id).where(
                    BusinessAuditEvent.organization_id == organization_id,
                    BusinessAuditEvent.subject_id == subject_id,
                )
            )
            assert owned_id is not None
            assert connection.scalar(
                select(AuditEvent.id).where(AuditEvent.id == owned_id)
            ) == owned_id
        finally:
            transaction.rollback()


def test_reconciliation_rejects_conflicting_and_unmirrored_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        token = login(client, create_user(client, "event-conflict"))
        organization_id = uuid.UUID(create_org(client, token, "event-conflict-org"))

    monkeypatch.setattr(settings, "business_event_write_mode", "dual")
    with make_engine().connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as db:
                subject_id = uuid.uuid4()
                append_business_event(
                    db, organization_id, None, "case.test_conflict", "case", subject_id
                )
                db.flush()
            owned_id = connection.scalar(
                select(BusinessAuditEvent.id).where(
                    BusinessAuditEvent.organization_id == organization_id,
                    BusinessAuditEvent.subject_id == subject_id,
                )
            )
            assert owned_id is not None
            connection.execute(
                update(AuditEvent)
                .where(AuditEvent.id == owned_id)
                .values(metadata_json={"changed": True})
            )
            report = collect_report(connection)
            assert report["conflicts"] == 1
            with pytest.raises(ValueError):
                restore_legacy_copy(connection)

            connection.execute(
                AuditEvent.__table__.insert().values(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    action="case.test_unmirrored",
                    subject_type="case",
                )
            )
            report = collect_report(connection)
            assert report["legacy_only"] == 1
        finally:
            transaction.rollback()
