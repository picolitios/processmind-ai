"""Coordinate durable identity commands with the audit configuration owner."""

import json
import time
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit_config_contract import ApplyConfiguration
from app.core.config import settings
from app.core.errors import ApiError
from app.core.internal_auth import command_signature
from app.db.engine import make_engine
from app.features.identity.models import Organization, OrganizationConfigCommand


class ConfigurationConflict(Exception):
    """The audit owner has a different version or value for this command."""


def apply_remote(command: OrganizationConfigCommand) -> None:
    """Send a signed, bounded command and verify the owner's acknowledgement."""
    payload = ApplyConfiguration(
        command_id=command.id,
        organization_id=command.organization_id,
        settings_version=command.settings_version,
        kind=command.kind,
        amount_limits=command.amount_limits,
        delay_window_days=command.delay_window_days,
    ).model_dump(mode="json")
    timestamp = str(int(time.time()))
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.post(
                f"{settings.audit_internal_url.rstrip('/')}/internal/v1/audit-config/apply",
                json=payload,
                headers={
                    "X-Internal-Timestamp": timestamp,
                    "X-Internal-Signature": command_signature(timestamp, payload),
                },
            )
    except httpx.RequestError as exc:
        raise ApiError(503, "audit_configuration_unavailable", "Configuração indisponível") from exc
    if response.status_code == 409:
        raise ConfigurationConflict
    if response.status_code != 200:
        raise ApiError(503, "audit_configuration_unavailable", "Configuração indisponível")
    try:
        result = response.json()
        valid = (
            result["organization_id"] == str(command.organization_id)
            and result["settings_version"] == command.settings_version
        )
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise ApiError(503, "audit_configuration_unavailable", "Configuração indisponível")


def incomplete_command(db: Session, organization_id: uuid.UUID) -> OrganizationConfigCommand | None:
    """Find an unresolved command while its organization row is locked."""
    return db.scalar(
        select(OrganizationConfigCommand)
        .where(
            OrganizationConfigCommand.organization_id == organization_id,
            OrganizationConfigCommand.status.in_(("pending", "blocked")),
        )
        .order_by(OrganizationConfigCommand.settings_version)
        .with_for_update()
    )


def complete_pending(db: Session, organization_id: uuid.UUID) -> Organization:
    """Apply and acknowledge one pending command with a consistent lock order."""
    organization = db.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None:
        raise ApiError(404, "not_found", "Organização não encontrada")
    command = incomplete_command(db, organization_id)
    if command is None:
        db.rollback()
        return organization
    if command.status == "blocked":
        db.rollback()
        raise ApiError(503, "audit_configuration_conflict", "Configuração indisponível")
    try:
        apply_remote(command)
    except ConfigurationConflict as exc:
        command.status = "blocked"
        db.commit()
        raise ApiError(503, "audit_configuration_conflict", "Configuração indisponível") from exc
    except ApiError:
        db.rollback()
        raise
    command.status = "applied"
    command.applied_at = datetime.now(UTC)
    if command.kind == "provision":
        organization.status = "active"
    db.commit()
    return organization


def pending_for_organizations(db: Session, organization_ids: list[uuid.UUID]) -> bool:
    """Protect public settings views from an unconfirmed version."""
    if not organization_ids:
        return False
    count = db.scalar(
        select(func.count())
        .select_from(OrganizationConfigCommand)
        .where(
            OrganizationConfigCommand.organization_id.in_(organization_ids),
            OrganizationConfigCommand.status.in_(("pending", "blocked")),
        )
    )
    return bool(count)


def run_once() -> bool:
    """Retry one recoverable command without scanning private audit tables."""
    with Session(make_engine()) as db:
        organization_id = db.scalar(
            select(OrganizationConfigCommand.organization_id)
            .where(OrganizationConfigCommand.status == "pending")
            .order_by(OrganizationConfigCommand.created_at, OrganizationConfigCommand.id)
            .limit(1)
        )
        if organization_id is None:
            return False
        try:
            complete_pending(db, organization_id)
        except ApiError:
            return False
        return True


def report() -> dict[str, int]:
    """Report unresolved operation counts without configuration values."""
    with Session(make_engine()) as db:
        rows = db.execute(
            select(OrganizationConfigCommand.status, func.count())
            .where(OrganizationConfigCommand.status.in_(("pending", "blocked")))
            .group_by(OrganizationConfigCommand.status)
        ).all()
    counts = {status: int(count) for status, count in rows}
    return {"pending": counts.get("pending", 0), "blocked": counts.get("blocked", 0)}


def main() -> None:
    """Run the dedicated reconciler or print a safe read-only status report."""
    import sys

    if len(sys.argv) == 2 and sys.argv[1] == "report":
        print(json.dumps(report(), sort_keys=True))
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: python -m app.features.identity.config_sync [report]")
    while True:
        try:
            worked = run_once()
        except Exception:
            # Retry transient database outages; never log credentials or command values.
            worked = False
        time.sleep(0.2 if worked else 2)


if __name__ == "__main__":
    main()
