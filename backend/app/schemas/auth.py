"""Pydantic schemas for authentication and organization membership."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.rbac import OrgRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    organization_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: uuid.UUID | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OrganizationMembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: OrgRole

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    is_email_verified: bool
    memberships: list[OrganizationMembershipOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}
