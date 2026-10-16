import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.audit_config_contract import AuditConfigFields

Role = Literal["owner", "admin", "analyst", "viewer"]
MemberStatus = Literal["active", "inactive"]


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, password: str) -> str:
        if not password.strip():
            raise ValueError("Password cannot be blank")
        return password


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserView(BaseModel):
    id: uuid.UUID
    email: EmailStr


class MemberView(BaseModel):
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    status: MemberStatus
    created_at: datetime


class MemberPage(BaseModel):
    items: list[MemberView]
    next_cursor: str | None


class SessionView(BaseModel):
    user: UserView
    memberships: list[MemberView]
    csrf_token: str


class OrganizationInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)

    @field_validator("name")
    @classmethod
    def reject_blank_name(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("Organization name cannot be blank")
        return name


class OrganizationSettingsInput(AuditConfigFields):
    """Public audit settings retain the existing validation contract."""


class OrganizationView(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    settings_version: int
    settings: dict[str, Any]


class MemberInput(BaseModel):
    email: EmailStr
    role: Role


class MemberPatch(BaseModel):
    role: Role | None = None
    status: MemberStatus | None = None
