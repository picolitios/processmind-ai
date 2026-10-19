"""Exercise the outbox and consumer against a real ephemeral RabbitMQ in CI."""

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity import create_org, create_user, csrf_headers, login

from app.core.config import settings
from app.db.engine import make_engine
from app.features.audit import broker
from app.features.audit.outbox import OutboxEvent
from app.features.ingestion.worker import run_once
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1" or os.getenv("RUN_BROKER_TESTS") != "1",
    reason="Dedicated PostgreSQL and RabbitMQ test services required",
)


def test_broker_outage_recovery_and_duplicate_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broker outage leaves the committed event pending; recovery reaches the API."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "audit_dispatch_mode", "broker")
    with TestClient(app) as client:
        token = login(client, create_user(client, "real-broker-owner"))
        org_id = create_org(client, token, "real-broker-org")
        base = f"/api/v1/organizations/{org_id}"
        csv_data = (
            b"purchase_id,supplier_id,purchase_date,product_id,quantity,unit_price,currency,"
            b"total_amount,expected_delivery_date,actual_delivery_date\n"
            b"P-1,S-1,2025-01-01,SKU-1,2,10,BRL,200,2025-01-05,2025-01-05\n"
        )
        uploaded = client.post(
            f"{base}/imports", headers=csrf_headers(token),
            files={"file": ("broker.csv", csv_data)},
        )
        assert uploaded.status_code == 201, uploaded.text
        mapping = {field: field for field in csv_data.decode().splitlines()[0].split(",")}
        confirmed = client.post(
            f"{base}/imports/{uploaded.json()['id']}/confirm",
            headers=csrf_headers(token), json={"columns": mapping},
        )
        assert confirmed.status_code == 202, confirmed.text
        assert run_once()
        created = client.post(
            f"{base}/audits",
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [uploaded.json()["id"]]},
        )
        assert created.status_code == 202, created.text
        audit_id = created.json()["id"]
        with Session(make_engine()) as db:
            event = db.scalar(
                select(OutboxEvent).where(OutboxEvent.organization_id == uuid.UUID(org_id))
            )
            assert event is not None
            event_id = event.id

        # Fail the transport after the API transaction has committed.
        original_connect = broker.connect

        def unavailable() -> None:
            raise ConnectionError("simulated broker outage")

        monkeypatch.setattr(broker, "connect", unavailable)
        with pytest.raises(ConnectionError):
            broker.publish_one()
        with Session(make_engine()) as db:
            pending = db.get(OutboxEvent, event_id)
            assert pending is not None and pending.published_at is None

        monkeypatch.setattr(broker, "connect", original_connect)
        assert broker.publish_one()
        with Session(make_engine()) as db:
            published = db.get(OutboxEvent, event_id)
            assert published is not None and published.published_at is not None

        connection = broker.connect()
        try:
            channel = connection.channel()
            broker.declare_topology(channel)
            method, _, body = channel.basic_get(broker.QUEUE, auto_ack=False)
            assert method is not None and body is not None
            broker.process_delivery(channel, method.delivery_tag, body)
            result = client.get(f"{base}/audits/{audit_id}")
            assert result.status_code == 200 and result.json()["status"] == "succeeded"
            findings = client.get(f"{base}/findings", params={"audit_id": audit_id})
            assert findings.status_code == 200
            assert "TOTAL_MISMATCH" in {item["rule_code"] for item in findings.json()["items"]}
            first_count = result.json()["finding_count"]

            # A duplicate broker delivery must not produce duplicate findings.
            broker.publish(channel, body, str(event_id))
            method, _, duplicate = channel.basic_get(broker.QUEUE, auto_ack=False)
            assert method is not None and duplicate is not None
            broker.process_delivery(channel, method.delivery_tag, duplicate)
            assert client.get(f"{base}/audits/{audit_id}").json()["finding_count"] == first_count
        finally:
            connection.close()

        # A closed consumer connection requeues its unacknowledged delivery.
        # The new consumer must reclaim the committed job without a one-hour wait.
        second = client.post(
            f"{base}/audits",
            headers={**csrf_headers(token), "Idempotency-Key": uuid.uuid4().hex},
            json={"import_ids": [uploaded.json()["id"]]},
        )
        assert second.status_code == 202, second.text
        assert broker.publish_one()
        original_processor = broker.process_audit_job

        def crash(*_: object) -> None:
            raise SystemExit("simulated consumer exit")

        monkeypatch.setattr(broker, "process_audit_job", crash)
        abandoned = broker.connect()
        try:
            channel = abandoned.channel()
            method, _, body = channel.basic_get(broker.QUEUE, auto_ack=False)
            assert method is not None and body is not None
            with pytest.raises(SystemExit):
                broker.process_delivery(channel, method.delivery_tag, body)
        finally:
            abandoned.close()

        monkeypatch.setattr(broker, "process_audit_job", original_processor)
        recovered = broker.connect()
        try:
            channel = recovered.channel()
            method, _, body = channel.basic_get(broker.QUEUE, auto_ack=False)
            assert method is not None and body is not None
            broker.process_delivery(channel, method.delivery_tag, body)
            result = client.get(f"{base}/audits/{second.json()['id']}")
            assert result.status_code == 200 and result.json()["status"] == "succeeded"
        finally:
            recovered.close()
