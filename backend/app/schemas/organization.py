"""Pydantic schemas for organization settings + member administration."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.rbac import OrgRole


class GSTProfileOut(BaseModel):
    gstin: str
    legal_name: str
    trade_name: str | None
    state_code: str
    registration_type: str
    is_verified: bool

    model_config = {"from_attributes": True}


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    legal_name: str | None
    slug: str
    is_active: bool
    gst_profile: GSTProfileOut | None = None

    model_config = {"from_attributes": True}


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)


class UpsertGSTProfileRequest(BaseModel):
    gstin: str = Field(min_length=15, max_length=15)
    legal_name: str = Field(min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    state_code: str = Field(default="", max_length=2)
    registration_type: str = Field(default="regular", max_length=50)


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: OrgRole
    is_active: bool

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.VIEWER
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=10, max_length=128)


class UpdateMemberRequest(BaseModel):
    role: OrgRole | None = None
    is_active: bool | None = None


class SettingsOut(BaseModel):
    settings: dict[str, dict]


class UpdateSettingRequest(BaseModel):
    key: str = Field(min_length=1, max_length=150)
    value: dict


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_type: str
    action: str
    entity_type: str | None
    entity_id: str | None
    metadata_json: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=10, max_length=128)
