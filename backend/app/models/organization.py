"""Organization (tenant) and GST profile models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.rbac import OrganizationMember


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A tenant. Every business object elsewhere carries organization_id."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    gst_profile: Mapped[GSTProfile | None] = relationship(
        back_populates="organization", uselist=False, cascade="all, delete-orphan"
    )


class GSTProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """GST registration details for an organization (one primary GSTIN per
    profile; an organization may hold multiple profiles for multi-state
    registrations in a future iteration)."""

    __tablename__ = "gst_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    gstin: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    registration_type: Mapped[str] = mapped_column(
        String(50), default="regular", nullable=False
    )  # regular | composition | casual | sez | ...
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="gst_profile")
