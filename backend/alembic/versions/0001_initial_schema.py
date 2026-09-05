"""initial schema — all core tables

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-02

This first migration creates the full baseline schema directly from the
SQLAlchemy ORM metadata (`Base.metadata.create_all`) rather than a hand
transcribed sequence of `op.create_table(...)` calls. For a from-scratch
initial migration these are equivalent — every table, column, enum,
index, unique constraint and foreign key is taken verbatim from the model
definitions in app/models, so there is no risk of the migration drifting
from the ORM the day it's created.

Every migration *after* this one should be generated the normal way,
against a real running Postgres instance:

    make migrate-new name="add_some_column"

which lets Alembic autogenerate a proper incremental diff (and lets a
human review it) instead of re-running create_all.
"""

from __future__ import annotations

from collections.abc import Sequence

import app.models  # noqa: F401 — populates Base.metadata with all tables
from alembic import op
from app.core.database import Base

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
