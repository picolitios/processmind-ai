"""Allowlisted JSON records for operational request and audit-event outcomes."""

import json
import logging
import sys
from datetime import UTC, datetime

logger = logging.getLogger("processmind.operational")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def _emit(fields: dict[str, str | int | float | None]) -> None:
    """Serialize only fields selected by the callers' fixed contracts."""
    logger.info(json.dumps({"observed_at": datetime.now(UTC).isoformat(), **fields}))


def log_request(
    service: str,
    correlation_id: str,
    method: str,
    route: str,
    status_code: int,
    duration_ms: float,
) -> None:
    """Record HTTP completion without a raw URL or client-controlled text."""
    _emit(
        {
            "service": service,
            "action": "http_request",
            "correlation_id": correlation_id,
            "method": method,
            "route": route,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }
    )


def log_audit_event(
    service: str,
    action: str,
    outcome: str,
    correlation_id: str | None,
    event_id: str | None,
    error_type: str | None = None,
) -> None:
    """Record a broker transition using identifiers and internal enums only."""
    _emit(
        {
            "service": service,
            "action": action,
            "outcome": outcome,
            "correlation_id": correlation_id,
            "event_id": event_id,
            "error_type": error_type,
        }
    )
