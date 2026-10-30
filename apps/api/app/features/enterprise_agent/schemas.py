"""Entradas estritas para configurações e documentos da empresa."""

import re
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


class GitHubDocumentInput(BaseModel):
    """Accept only repository identifiers and text paths, never a caller URL."""

    model_config = ConfigDict(extra="forbid")

    owner: str
    repo: str
    path: str
    title: Title
    enabled: bool = False

    @field_validator("title")
    @classmethod
    def plain_title(cls, value: str) -> str:
        return KnowledgeInput.plain_text(value)

    @field_validator("owner")
    @classmethod
    def owner_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", value):
            raise ValueError("invalid_owner")
        return value.lower()

    @field_validator("repo")
    @classmethod
    def repo_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value) or value in {".", ".."}:
            raise ValueError("invalid_repo")
        return value.lower()

    @field_validator("path")
    @classmethod
    def document_path(cls, value: str) -> str:
        parts = value.split("/")
        if (
            len(value) > 240 or not value.lower().endswith((".md", ".txt"))
            or any(
                part in {"", ".", ".."}
                or re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None
                for part in parts
            )
        ):
            raise ValueError("invalid_document_path")
        return value
