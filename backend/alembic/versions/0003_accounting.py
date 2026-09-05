"""add double-entry accounting tables

Revision ID: 0003_accounting
Revises: 0002_gst_returns
Create Date: 2026-09-04

Adds the Tally-style bookkeeping layer: ledger_groups, ledgers, vouchers,
voucher_entries (and the `account_nature` / `balance_side` / `voucher_type`
enums).

Same convention as the earlier migrations — the tables are created from ORM
metadata via ``create_all(checkfirst=True)``, a no-op on a fresh database
where ``0001`` already materialised them and an additive create on a
database migrated before this feature existed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.models  # noqa: F401 — populates Base.metadata
from alembic import op
from app.core.database import Base

revision: str = "0003_accounting"
down_revision: str | None = "0002_gst_returns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TABLES = ("ledger_groups", "ledgers", "vouchers", "voucher_entries")
_NEW_ENUMS = ("account_nature", "balance_side", "voucher_type")


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
