"""Private idempotent owner endpoint for versioned audit settings."""

from fastapi import APIRouter, Header
from sqlalchemy import text

from app.core.audit_config_contract import ApplyConfiguration
from app.core.errors import ApiError
from app.core.internal_auth import verify_command_signature
from app.features.audit.models import AuditConfiguration
from app.features.identity.security import DB

router = APIRouter(prefix="/internal/v1/audit-config", include_in_schema=False)


@router.post("/apply", status_code=200)
def apply_configuration(
    data: ApplyConfiguration,
    db: DB,
    x_internal_timestamp: str = Header(),
    x_internal_signature: str = Header(),
) -> dict[str, int | str]:
    """Apply exactly one next version, or acknowledge an identical retry."""
    verify_command_signature(
        x_internal_timestamp, x_internal_signature, data.model_dump(mode="json")
    )
    # The tenant key serializes first-time provisioning as well as version updates.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"processmind:audit-config:{data.organization_id}"},
    )
    current = db.get(AuditConfiguration, data.organization_id, with_for_update=True)
    if current is None:
        if data.kind != "provision" or data.settings_version != 1:
            raise ApiError(409, "config_version_conflict", "Versão de configuração divergente")
        db.add(
            AuditConfiguration(
                organization_id=data.organization_id,
                settings_version=1,
                last_command_id=data.command_id,
                amount_limits=data.amount_limits,
                delay_window_days=data.delay_window_days,
            )
        )
    elif current.settings_version == data.settings_version:
        if (
            current.last_command_id != data.command_id
            or current.amount_limits != data.amount_limits
            or current.delay_window_days != data.delay_window_days
        ):
            raise ApiError(409, "config_version_conflict", "Versão de configuração divergente")
    elif data.kind == "update" and current.settings_version == data.settings_version - 1:
        current.settings_version = data.settings_version
        current.last_command_id = data.command_id
        current.amount_limits = data.amount_limits
        current.delay_window_days = data.delay_window_days
    else:
        raise ApiError(409, "config_version_conflict", "Versão de configuração divergente")
    db.commit()
    return {"organization_id": str(data.organization_id), "settings_version": data.settings_version}
