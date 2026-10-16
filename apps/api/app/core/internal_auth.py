"""Signed, short-lived service commands for the private audit boundary."""

import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings
from app.core.errors import ApiError


def command_signature(timestamp: str, command: dict[str, Any]) -> str:
    """Bind the HMAC to the complete canonical command and its issue time."""
    payload = json.dumps(command, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    message = f"audit-config:v1\n{timestamp}\n{payload}".encode()
    return hmac.new(settings.auth_hash_key.encode(), message, hashlib.sha256).hexdigest()


def verify_command_signature(
    timestamp: str, supplied: str, command: dict[str, Any]
) -> None:
    """Reject stale or modified private commands without exposing their contents."""
    try:
        issued_at = int(timestamp)
    except ValueError as exc:
        raise ApiError(403, "forbidden", "Serviço não autorizado") from exc
    if abs(time.time() - issued_at) > 30 or not (
        len(supplied) == 64
        and hmac.compare_digest(supplied, command_signature(timestamp, command))
    ):
        raise ApiError(403, "forbidden", "Serviço não autorizado")
