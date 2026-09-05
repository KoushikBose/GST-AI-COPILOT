"""Organization membership and role-based access control.

Role is modeled as a bounded enum on the membership row rather than a fully
generic roles/permissions graph — this is a deliberate "don't over-engineer"
choice (see master spec section 42: modular monolith, extract later). If
fine-grained per-permission overrides are needed later, add a
`permission_overrides` table keyed on (membership_id, permission) without
touching this model's shape.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class OrgRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    ACCOUNTANT = "accountant"
    FINANCE_MANAGER = "finance_manager"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    VIEWER = "viewer"


# Roles permitted to approve human-in-the-loop review items / return filings.
APPROVER_ROLES = {OrgRole.SUPER_ADMIN, OrgRole.ORG_ADMIN, OrgRole.ACCOUNTANT, OrgRole.REVIEWER}

# Roles permitted to manage organization settings, users, documents.
ADMIN_ROLES = {OrgRole.SUPER_ADMIN, OrgRole.ORG_ADMIN}


class OrganizationMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member_org_user"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[OrgRole] = mapped_column(
        str_enum_column(OrgRole, "org_role"), nullable=False, default=OrgRole.VIEWER
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="members")  # noqa: F821
    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])  # noqa: F821

    def has_role(self, *roles: OrgRole) -> bool:
        return self.role in roles
