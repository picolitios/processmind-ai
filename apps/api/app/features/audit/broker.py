"""Publica pedidos de auditoria no RabbitMQ e confirma entregas ao consumidor."""

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pika  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.observability import log_audit_event
from app.db.engine import make_engine
from app.features.audit.models import AuditRun
from app.features.audit.outbox import OutboxEvent
from app.features.audit.worker import process_audit_job
from app.features.ingestion.models import Job

EXCHANGE = "processmind.events"
ROUTING_KEY = "audit.requested.v1"
QUEUE = "processmind.audit.requested.v1"
RETRY_5 = "processmind.audit.retry.5s"
RETRY_15 = "processmind.audit.retry.15s"
DEAD = "processmind.audit.dead"


class Payload(BaseModel):
    audit_id: uuid.UUID
    job_id: uuid.UUID


class AuditRequested(BaseModel):
    event_id: uuid.UUID
    event_type: str
    event_version: int
    occurred_at: datetime
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None
    tenant_id: uuid.UUID
    payload: Payload


def connect() -> Any:
    params = pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        credentials=pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password),
        heartbeat=0,  # Audit evaluation may exceed broker heartbeat intervals.
        socket_timeout=5,
        blocked_connection_timeout=30,
    )
    return pika.BlockingConnection(params)


def declare_topology(channel: Any) -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=ROUTING_KEY)
    for queue, delay in ((RETRY_5, 5000), (RETRY_15, 15000)):
        channel.queue_declare(
            queue=queue,
            durable=True,
            arguments={
                "x-message-ttl": delay,
                "x-dead-letter-exchange": EXCHANGE,
                "x-dead-letter-routing-key": ROUTING_KEY,
            },
        )
    channel.queue_declare(queue=DEAD, durable=True)
    channel.confirm_delivery()


def publish(channel: Any, body: bytes, event_id: str, queue: str | None = None) -> None:
    channel.basic_publish(
        exchange="" if queue else EXCHANGE,
        routing_key=queue or ROUTING_KEY,
        body=body,
        mandatory=True,
        properties=pika.BasicProperties(
            content_type="application/json", delivery_mode=2, message_id=event_id
        ),
    )


def publish_one() -> bool:
    with Session(make_engine()) as db:
        item = db.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if item is None:
            return False
        connection = connect()
        try:
            channel = connection.channel()
            declare_topology(channel)
            publish(channel, json.dumps(item.envelope).encode(), str(item.id))
            item.published_at = datetime.now(UTC)
            db.commit()
            log_audit_event(
                "audit-publisher",
                "audit_publish",
                "published",
                item.envelope.get("correlation_id"),
                str(item.id),
            )
        finally:
            connection.close()
    return True


def publisher_main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("pika").setLevel(logging.WARNING)
    while True:
        try:
            if not publish_one():
                time.sleep(2)
        except Exception as exc:
            log_audit_event(
                "audit-publisher", "audit_publish", "failed", None, None,
                type(exc).__name__,
            )
            time.sleep(5)


def validate_event(body: bytes) -> AuditRequested | None:
    try:
        event = AuditRequested.model_validate_json(body)
    except ValidationError:
        return None
    if event.event_type != "audit.requested" or event.event_version != 1:
        return None
    return event


def log_delivery(event: AuditRequested, outcome: str, error_type: str | None = None) -> None:
    """Record a validated envelope's correlation without its tenant or payload."""
    log_audit_event(
        "audit-consumer",
        "audit_delivery",
        outcome,
        str(event.correlation_id),
        str(event.event_id),
        error_type,
    )


def process_delivery(channel: Any, delivery_tag: int, body: bytes) -> None:
    event = validate_event(body)
    if event is None:
        publish(channel, body, str(uuid.uuid4()), DEAD)
        channel.basic_ack(delivery_tag=delivery_tag)
        log_audit_event("audit-consumer", "audit_delivery", "invalid", None, None)
        return
    with Session(make_engine()) as db:
        exists_for_tenant = db.scalar(
            select(Job.id).where(
                Job.id == event.payload.job_id,
                Job.type == "audit",
                Job.organization_id == event.tenant_id,
            )
        )
        job = db.scalar(
            select(Job).where(
                Job.id == event.payload.job_id,
                Job.type == "audit",
                Job.organization_id == event.tenant_id,
            )
            .with_for_update(skip_locked=True)
        )
        if job is None and exists_for_tenant is not None:
            # An active transaction owns the row; do not spend another attempt.
            db.rollback()
            publish(channel, body, str(event.event_id), RETRY_5)
            channel.basic_ack(delivery_tag=delivery_tag)
            log_delivery(event, "locked_retry")
            return
        run = db.scalar(
            select(AuditRun).where(
                AuditRun.id == event.payload.audit_id,
                AuditRun.organization_id == event.tenant_id,
            )
        )
        if (
            job is None
            or job.organization_id != event.tenant_id
            or run is None
            or run.job_id != job.id
        ):
            db.rollback()
            publish(channel, body, str(event.event_id), DEAD)
            channel.basic_ack(delivery_tag=delivery_tag)
            log_delivery(event, "rejected")
            return
        if job.status == "succeeded":
            db.rollback()
            channel.basic_ack(delivery_tag=delivery_tag)
            log_delivery(event, "duplicate")
            return
        if job.status == "failed":
            db.rollback()
            publish(channel, body, str(event.event_id), DEAD)
            channel.basic_ack(delivery_tag=delivery_tag)
            log_delivery(event, "already_failed")
            return
        now = datetime.now(UTC)
        # A requeued delivery can reclaim an abandoned attempt immediately.
        # The claim token fences the prior owner in the gap before its row lock.
        if job.attempt_count >= 3:
            job.status = "failed"
            job.error_code = "lease_expired"
            job.lease_until = None
            job.attempt_token = None
            run.status = "failed"
            run.finished_at = now
            run.limitation = "Falha no processamento (lease_expired)."
            db.commit()
            publish(channel, body, str(event.event_id), DEAD)
            channel.basic_ack(delivery_tag=delivery_tag)
            log_delivery(event, "lease_exhausted")
            return
        job.status = "running"
        job.attempt_count += 1
        job.attempt_token = uuid.uuid4()
        job.lease_until = now + timedelta(hours=1)
        job.error_code = None
        attempt = job.attempt_count
        attempt_token = job.attempt_token
        db.commit()
        try:
            completed = process_audit_job(db, job.id, attempt_token)
            outcome = "succeeded" if completed else "superseded"
            error_type = None
        except Exception as exc:
            db.rollback()
            job = db.scalar(
                select(Job).where(
                    Job.id == event.payload.job_id,
                    Job.organization_id == event.tenant_id,
                ).with_for_update()
            )
            run = db.scalar(
                select(AuditRun).where(
                    AuditRun.id == event.payload.audit_id,
                    AuditRun.organization_id == event.tenant_id,
                )
            )
            if job is None or run is None:
                raise
            if job.attempt_token != attempt_token:
                db.rollback()
                channel.basic_ack(delivery_tag=delivery_tag)
                log_delivery(event, "superseded")
                return
            permanent = isinstance(exc, ValueError)
            job.status = "failed" if permanent or attempt >= 3 else "queued"
            job.error_code = type(exc).__name__[:80]
            job.lease_until = None
            job.attempt_token = None
            run.status = job.status
            if job.status == "failed":
                run.finished_at = datetime.now(UTC)
                run.limitation = f"Falha no processamento ({job.error_code})."
            db.commit()
            retry = DEAD if job.status == "failed" else (RETRY_5 if attempt == 1 else RETRY_15)
            publish(channel, body, str(event.event_id), retry)
            outcome = "failed" if job.status == "failed" else "retry"
            error_type = type(exc).__name__
        channel.basic_ack(delivery_tag=delivery_tag)
        log_delivery(event, outcome, error_type)


def consumer_main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("pika").setLevel(logging.WARNING)
    while True:
        try:
            connection = connect()
            try:
                channel = connection.channel()
                declare_topology(channel)
                channel.basic_qos(prefetch_count=1)
                for method, _, body in channel.consume(QUEUE, inactivity_timeout=5, auto_ack=False):
                    if method is not None:
                        process_delivery(channel, method.delivery_tag, body)
            finally:
                connection.close()
        except Exception as exc:
            log_audit_event(
                "audit-consumer", "audit_connection", "failed", None, None,
                type(exc).__name__,
            )
            time.sleep(5)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2 and sys.argv[1] == "publish":
        publisher_main()
    elif len(sys.argv) == 2 and sys.argv[1] == "consume":
        consumer_main()
    else:
        raise SystemExit("usage: python -m app.features.audit.broker [publish|consume]")
