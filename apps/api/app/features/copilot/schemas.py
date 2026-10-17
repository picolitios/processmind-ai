import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.features.ai.schemas import UUID_REFERENCE


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temporary_default: bool
    memory_turn_limit: int = Field(ge=0, le=20)


class ConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: uuid.UUID | None = None
    audit_id: uuid.UUID | None = None
    mode: Literal["normal", "temporary"]

    @model_validator(mode="after")
    def one_target(self) -> "ConversationInput":
        if self.model_fields_set - {"mode"} not in ({"finding_id"}, {"audit_id"}) or (
            (self.finding_id is None) == (self.audit_id is None)
        ):
            raise ValueError("exactly one target is required")
        return self


QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: QuestionText


class CopilotResult(BaseModel):
    """Only evidence identifiers from the supplied context may appear in the answer."""

    model_config = ConfigDict(extra="forbid")

    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    def validate_evidence(self, allowed: set[uuid.UUID]) -> None:
        if not set(self.evidence_ids) <= allowed or len(set(self.evidence_ids)) != len(
            self.evidence_ids
        ):
            raise ValueError("invalid_evidence_reference")
        if any(
            uuid.UUID(match.group()) not in allowed
            for match in UUID_REFERENCE.finditer(self.answer)
        ):
            raise ValueError("invalid_evidence_reference")
        # Markdown links and URLs are omitted in this bounded first version; only
        # server-produced citation links are displayed by the web interface.
        if re.search(r"https?://|\]\(", self.answer, re.IGNORECASE):
            raise ValueError("unexpected_link")
