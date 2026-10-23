import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

from app.core.audit_config_contract import AuditConfigFields

Role = Literal["owner", "admin", "analyst", "viewer"]
MemberStatus = Literal["active", "inactive"]


class RegisterInput(BaseModel):
    email: EmailStr
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)
    ] | None = None
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
    display_name: str | None = None
    email_verified: bool = False


class ProfileInput(BaseModel):
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)
    ]


class MemberView(BaseModel):
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    status: MemberStatus
    created_at: datetime
    display_name: str | None = None
    email: EmailStr | None = None


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


InviteRole = Literal["admin", "analyst", "viewer"]


class InviteInput(BaseModel):
    email: EmailStr
    role: InviteRole


class InviteView(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    role: InviteRole
    created_at: datetime
    expires_at: datetime
    sent_at: datetime | None
    accepted_at: datetime | None
    cancelled_at: datetime | None


class AcceptInviteInput(BaseModel):
    token: str = Field(min_length=40, max_length=128)
