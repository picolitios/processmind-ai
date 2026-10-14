import re
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class AIInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: uuid.UUID | None = None
    audit_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_target(self) -> "AIInput":
        if self.model_fields_set not in ({"finding_id"}, {"audit_id"}) or (
            (self.finding_id is None) == (self.audit_id is None)
        ):
            raise ValueError("exactly one target is required")
        return self


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
UUID_REFERENCE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class AIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: ShortText
    possible_causes: list[ShortText] = Field(max_length=5)
    suggested_checks: list[ShortText] = Field(max_length=5)
    corrective_actions: list[ShortText] = Field(max_length=5)
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    def validate_evidence(self, allowed: set[uuid.UUID]) -> None:
        if not set(self.evidence_ids) <= allowed or len(set(self.evidence_ids)) != len(
            self.evidence_ids
        ):
            raise ValueError("invalid_evidence_reference")
        text_fields = [
            self.summary,
            *self.possible_causes,
            *self.suggested_checks,
            *self.corrective_actions,
        ]
        if any(
            uuid.UUID(match.group()) not in allowed
            for value in text_fields
            for match in UUID_REFERENCE.finditer(value)
        ):
            raise ValueError("invalid_evidence_reference")
