"""add GSTR-2A/2B reconciliation tables

Revision ID: 0004_gstr_reconciliation
Revises: 0003_accounting
Create Date: 2026-09-05

Adds the GSTR-2A/2B reconciliation feature: gstr2b_records (imported
supplier-reported CSV rows), reconciliation_runs (one per period),
reconciliation_matches (one row per matched/mismatched/missing invoice),
and the `reconciliation_source` / `reconciliation_match_status` enums.

Same convention as the earlier migrations — the tables are created from ORM
metadata via ``create_all(checkfirst=True)``, a no-op where they already
exist and an additive create on a database migrated before this feature
existed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.models  # noqa: F401 — populates Base.metadata
from alembic import op
from app.core.database import Base

revision: str = "0004_gstr_reconciliation"
down_revision: str | None = "0003_accounting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TABLES = ("gstr2b_records", "reconciliation_runs", "reconciliation_matches")
_NEW_ENUMS = ("reconciliation_source", "reconciliation_match_status")


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _NEW_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_NEW_TABLES):
        op.drop_table(table)
    for enum_name in _NEW_ENUMS:
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
