"""Shared audit-settings validation and private command wire schema."""

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditConfigFields(BaseModel):
    amount_limits: dict[str, str] | None = None
    delay_window_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("amount_limits")
    @classmethod
    def validate_limits(cls, limits: dict[str, str] | None) -> dict[str, str] | None:
        if limits is None:
            return None
        if len(limits) > 50:
            raise ValueError("Too many currency limits")
        for currency, amount in limits.items():
            if not re.fullmatch(r"[A-Z]{3}", currency) or not re.fullmatch(
                r"\d{1,18}(?:\.\d{1,2})?", amount
            ):
                raise ValueError("Invalid currency or amount")
        return limits


class ApplyConfiguration(AuditConfigFields):
    model_config = ConfigDict(extra="forbid")

    command_id: uuid.UUID
    organization_id: uuid.UUID
    settings_version: int = Field(ge=1)
    kind: Literal["provision", "update"]
