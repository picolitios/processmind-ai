"""Entradas estritas para configurações e documentos da empresa."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class ConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_enabled: bool
    purchasing_enabled: bool


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class KnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    content: Content
    enabled: bool = False

    @field_validator("title", "content")
    @classmethod
    def plain_text(cls, value: str) -> str:
        # Control characters have no useful meaning in a process document and can hide instructions.
        if any(ord(char) < 32 and char not in "\n\t\r" for char in value):
            raise ValueError("control_characters_not_allowed")
        return value


class KnowledgePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    content: Content | None = None
    enabled: bool | None = None

    @field_validator("title", "content")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        return KnowledgeInput.plain_text(value) if value is not None else None
