import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import settings
from app.db.engine import make_engine
from app.features.audit import broker
from app.features.audit.broker import DEAD, RETRY_5, process_delivery, validate_event
from app.features.audit.models import AuditFinding, AuditRun
from app.features.audit.operations import database_metrics
from app.features.audit.outbox import OutboxEvent
from app.features.ingestion.models import Job
from app.features.ingestion.worker import run_once
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def test_audit_event_is_atomic_tenant_checked_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with TestClient(app) as client:
        token = login(client, create_user(client, "event-owner"))
        org_id = create_org(client, token, "event-org")
        base = f"/api/v1/organizations/{org_id}"
        csv_data = (
            b"purchase_id,supplier_id,purchase_date,product_id,quantity,unit_price,currency,"
            b"total_amount,expected_delivery_date,actual_delivery_date\n"
            b"P-1,S-1,2025-01-01,SKU-1,2,10,BRL,20,2025-01-05,2025-01-05\n"
        )
        upload = client.post(
            f"{base}/imports", headers=csrf_headers(token), files={"file": ("event.csv", csv_data)}
        )
        assert upload.status_code == 201, upload.text
        import_id = upload.json()["id"]
        mapping = {field: field for field in csv_data.decode().splitlines()[0].split(",")}
        confirmed = client.post(
            f"{base}/imports/{import_id}/confirm",
            headers=csrf_headers(token),
            json={"columns": mapping},
        )
        assert confirmed.status_code == 202, confirmed.text
        assert run_once()

        monkeypatch.setattr(settings, "audit_dispatch_mode", "broker")
        headers = {**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex}
        created = client.post(f"{base}/audits", headers=headers, json={"import_ids": [import_id]})
        assert created.status_code == 202, created.text
        replay = client.post(f"{base}/audits", headers=headers, json={"import_ids": [import_id]})
        assert replay.json()["id"] == created.json()["id"]
        audit_id = uuid.UUID(created.json()["id"])
        assert not run_once()  # Broker-mode worker cannot steal audit jobs.
        with Session(make_engine()) as db:
            events = db.scalars(
                select(OutboxEvent).where(OutboxEvent.organization_id == uuid.UUID(org_id))
            ).all()
            assert len(events) == 1
            event = events[0]
            assert event.published_at is None
            assert event.envelope["payload"] == {
                "audit_id": created.json()["id"],
                "job_id": created.json()["job_id"],
            }
            assert event.envelope["correlation_id"] == created.headers["X-Correlation-ID"]
            metrics = database_metrics(db, datetime.now(UTC))
            assert metrics["outbox"]["pending"] >= 1
            assert metrics["audit_jobs"]["oldest_queued_age_seconds"] is not None
            body = json.dumps(event.envelope).encode()

        def unavailable() -> None:
            raise ConnectionError("broker unavailable")

        monkeypatch.setattr(broker, "connect", unavailable)
        with pytest.raises(ConnectionError):
            broker.publish_one()
        with Session(make_engine()) as db:
            assert db.get(OutboxEvent, event.id).published_at is None  # type: ignore[union-attr]

        channel = Mock()
        original_processor = broker.process_audit_job

        def transient_failure(*_: object) -> None:
            raise RuntimeError("simulated worker interruption")

        monkeypatch.setattr(broker, "process_audit_job", transient_failure)
        process_delivery(channel, 1, body)
        assert channel.basic_ack.call_count == 1
        assert channel.basic_publish.call_args.kwargs["routing_key"] == RETRY_5
        assert client.get(f"{base}/audits/{created.json()['id']}").json()["status"] == "queued"

        # A delivery racing active processing must keep the current attempt.
        with Session(make_engine()) as active_db:
            locked = active_db.scalar(
                select(Job).where(Job.id == uuid.UUID(created.json()["job_id"]))
                .with_for_update()
            )
            assert locked is not None and locked.attempt_count == 1
            channel.reset_mock()
            process_delivery(channel, 2, body)
            assert channel.basic_publish.call_args.kwargs["routing_key"] == RETRY_5
            assert locked.attempt_count == 1
            active_db.rollback()

        # A process exit after the claim leaves a future lease and no ACK.
        def crash(*_: object) -> None:
            raise SystemExit("simulated consumer exit")

        monkeypatch.setattr(broker, "process_audit_job", crash)
        channel.reset_mock()
        with pytest.raises(SystemExit):
            process_delivery(channel, 3, body)
        assert channel.basic_ack.call_count == 0
        with Session(make_engine()) as db:
            crashed = db.get(Job, uuid.UUID(created.json()["job_id"]))
            assert crashed is not None and crashed.status == "running"
            assert crashed.lease_until is not None and crashed.lease_until > datetime.now(UTC)
            assert crashed.attempt_count == 2 and crashed.attempt_token is not None
            old_token = crashed.attempt_token

        def complete_after_fencing(db: Session, job_id: uuid.UUID, token: uuid.UUID) -> bool:
            with Session(make_engine()) as stale_db:
                assert not original_processor(stale_db, job_id, old_token)
            return original_processor(db, job_id, token)

        # RabbitMQ re-delivers the unacknowledged body on connection loss.
        # Recovery must not wait for the one-hour database lease.
        monkeypatch.setattr(broker, "process_audit_job", complete_after_fencing)
        channel.reset_mock()
        process_delivery(channel, 4, body)
        assert channel.basic_ack.call_count == 1
        with Session(make_engine()) as db:
            recovered = db.get(Job, uuid.UUID(created.json()["job_id"]))
            assert recovered is not None and recovered.attempt_count == 3
            assert recovered.attempt_token is None
        result = client.get(f"{base}/audits/{created.json()['id']}")
        assert result.status_code == 200 and result.json()["status"] == "succeeded"
        with Session(make_engine()) as db:
            count = len(
                db.scalars(
                    select(AuditFinding).where(AuditFinding.run_id == audit_id)
                ).all()
            )
        process_delivery(channel, 5, body)
        assert channel.basic_ack.call_count == 2
        with Session(make_engine()) as db:
            assert len(
                db.scalars(
                    select(AuditFinding).where(AuditFinding.run_id == audit_id)
                ).all()
            ) == count

        invalid = json.loads(body)
        invalid["tenant_id"] = str(uuid.uuid4())
        process_delivery(channel, 6, json.dumps(invalid).encode())
        assert channel.basic_ack.call_count == 3
        assert channel.basic_publish.call_args.kwargs["routing_key"] == DEAD
        assert validate_event(b'{}') is None

        # Repeated process exits consume the bounded attempt budget.
        exhausted_audit = client.post(
            f"{base}/audits",
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [import_id]},
        )
        assert exhausted_audit.status_code == 202, exhausted_audit.text
        with Session(make_engine()) as db:
            exhausted_event = next(
                event for event in db.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.organization_id == uuid.UUID(org_id)
                    )
                )
                if event.envelope["payload"]["audit_id"] == exhausted_audit.json()["id"]
            )
            exhausted_body = json.dumps(exhausted_event.envelope).encode()
        monkeypatch.setattr(broker, "process_audit_job", crash)
        for attempt in range(3):
            with pytest.raises(SystemExit):
                process_delivery(channel, 7 + attempt, exhausted_body)
        channel.reset_mock()
        process_delivery(channel, 10, exhausted_body)
        assert channel.basic_publish.call_args.kwargs["routing_key"] == DEAD
        assert client.get(f"{base}/audits/{exhausted_audit.json()['id']}").json()[
            "status"
        ] == "failed"

        # A stale worker exception must not overwrite a newer terminal state.
        stale_audit = client.post(
            f"{base}/audits",
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [import_id]},
        )
        assert stale_audit.status_code == 202, stale_audit.text
        with Session(make_engine()) as db:
            stale_event = next(
                event for event in db.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.organization_id == uuid.UUID(org_id)
                    )
                )
                if event.envelope["payload"]["audit_id"] == stale_audit.json()["id"]
            )
            stale_body = json.dumps(stale_event.envelope).encode()

        def newer_terminal(*_: object) -> None:
            with Session(make_engine()) as newer_db:
                newer_job = newer_db.get(Job, uuid.UUID(stale_audit.json()["job_id"]))
                newer_run = newer_db.get(AuditRun, uuid.UUID(stale_audit.json()["id"]))
                assert newer_job is not None and newer_run is not None
                newer_job.status = "failed"
                newer_job.attempt_token = None
                newer_run.status = "failed"
                newer_db.commit()
            raise RuntimeError("old attempt failed after losing claim")

        monkeypatch.setattr(broker, "process_audit_job", newer_terminal)
        channel.reset_mock()
        process_delivery(channel, 11, stale_body)
        assert channel.basic_ack.call_count == 1
        with Session(make_engine()) as db:
            stale_job = db.get(Job, uuid.UUID(stale_audit.json()["job_id"]))
            assert stale_job is not None and stale_job.status == "failed"
            assert stale_job.error_code is None
