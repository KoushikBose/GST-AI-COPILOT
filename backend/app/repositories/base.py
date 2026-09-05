"""Generic repository base classes.

`TenantScopedRepository` is the structural enforcement point for multi-tenant
isolation: every read/write it exposes requires an `organization_id` and
filters on it, so a service cannot accidentally query across tenants just by
forgetting a `WHERE` clause. Business repositories should subclass this
rather than querying `AsyncSession` directly wherever tenant data is involved.
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.errors import NotFoundError, TenantIsolationError

ModelT = TypeVar("ModelT", bound=Base)


class TenantScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, entity_id: uuid.UUID, *, organization_id: uuid.UUID
    ) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == entity_id,  # type: ignore[attr-defined]
            self.model.organization_id == organization_id,  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(
        self, entity_id: uuid.UUID, *, organization_id: uuid.UUID
    ) -> ModelT:
        entity = await self.get_by_id(entity_id, organization_id=organization_id)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} not found.")
        return entity

    async def assert_belongs_to_org(self, entity: ModelT, *, organization_id: uuid.UUID) -> None:
        if getattr(entity, "organization_id", None) != organization_id:
            raise TenantIsolationError(
                "The requested resource does not belong to this organization."
            )

    async def list_for_org(
        self,
        *,
        organization_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModelT]:
        stmt = (
            select(self.model)
            .where(self.model.organization_id == organization_id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
