"""add gst_returns table

Revision ID: 0002_gst_returns
Revises: 0001_initial_schema
Create Date: 2026-09-04

Adds the `gst_returns` table backing the return-preparation feature
(GSTR-1 / GSTR-3B draft aggregation + human approval).

Consistent with `0001_initial_schema`, the table (and its enums) are
created from the ORM metadata via `create_all(checkfirst=True)` — on a
brand-new database `0001` already materialised it, so this is a no-op
there; on a database that was migrated before this feature existed it
creates just the new table. `downgrade` drops it explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.models  # noqa: F401 — populates Base.metadata
from alembic import op
from app.core.database import Base

revision: str = "0002_gst_returns"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TABLES = ("gst_returns",)
_NEW_ENUMS = ("gst_return_type", "gst_return_status")


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _NEW_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in _NEW_TABLES:
        op.drop_table(table)
    for enum_name in _NEW_ENUMS:
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
