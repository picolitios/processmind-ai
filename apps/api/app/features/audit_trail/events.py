import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.features.audit_trail.models import BusinessAuditEvent
from app.features.identity.models import AuditEvent


def append_business_event(
    db: Session,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    subject_type: str,
    subject_id: uuid.UUID | None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    """Append the owned event; optionally mirror it for legacy-code rollback."""
    event_id = uuid.uuid4()
    occurred_at = datetime.now(UTC)
    fields = {
        "id": event_id,
        "organization_id": organization_id,
        "actor_user_id": actor_user_id,
        "action": action,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "metadata_json": metadata or {},
        "correlation_id": correlation_id,
        "occurred_at": occurred_at,
    }
    db.add(BusinessAuditEvent(**fields))
    # Dual mode remains available until the previous application version is retired.
    if settings.business_event_write_mode == "dual":
        db.add(AuditEvent(**fields))


def log_business_event(
    db: Session,
    request: Request,
    action: str,
    actor_user_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    """Record a request-scoped business event with its correlation ID."""
    append_business_event(
        db,
        organization_id,
        actor_user_id,
        action,
        subject_type,
        subject_id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
