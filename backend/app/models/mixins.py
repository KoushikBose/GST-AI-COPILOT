"""Reusable ORM mixins: UUID PKs, timestamps, audit columns, soft delete,
and tenant scoping.

Every business table (i.e. everything except `organizations` itself and
platform-level tables) includes `TenantScopedMixin` so tenant isolation is
structural rather than something each query has to remember to add.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

_EnumT = TypeVar("_EnumT", bound=StrEnum)


def str_enum_column(enum_cls: type[_EnumT], name: str) -> SAEnum:
    """SQLAlchemy Enum column that persists `.value` (e.g. "org_admin"),
    not `.name` (e.g. "ORG_ADMIN") — SQLAlchemy's default is the latter,
    which would silently diverge from every other layer (JWTs, JSON API
    responses, StrEnum.__str__) that serializes these enums by value.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda cls: [e.value for e in cls])


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditActorMixin:
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantScopedMixin:
    """Adds organization_id (tenant_id) to a table.

    Every repository query against a tenant-scoped table MUST filter on
    organization_id — see app/repositories/base.py, which enforces this
    centrally so individual services cannot forget it.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
