"""Double-entry accounting service — the "Tally-like" bookkeeping layer.

Responsibilities:

* seed a Tally-style chart of accounts for an organization (idempotent),
* create manual vouchers (with balance validation delegated to
  ``app.rules.accounting``),
* post an invoice to a Sales / Purchase voucher automatically,
* aggregate voucher entries into the Trial Balance, Profit & Loss,
  Balance Sheet, Day Book and per-ledger statement.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.accounting import (
    AccountNature,
    BalanceSide,
    Ledger,
    LedgerGroup,
    Voucher,
    VoucherEntry,
    VoucherType,
)
from app.models.audit import AuditLog
from app.models.invoice import Invoice, InvoiceDirection
from app.rules import accounting as engine

logger = get_logger(__name__)

_EPOCH = "1900-01-01"
_FAR_FUTURE = "9999-12-31"

_VOUCHER_PREFIX = {
    VoucherType.SALES: "SAL",
    VoucherType.PURCHASE: "PUR",
    VoucherType.RECEIPT: "RCT",
    VoucherType.PAYMENT: "PMT",
    VoucherType.CONTRA: "CTR",
    VoucherType.JOURNAL: "JV",
    VoucherType.DEBIT_NOTE: "DN",
    VoucherType.CREDIT_NOTE: "CN",
}

# name, nature, classification, sort_order
_DEFAULT_GROUPS: list[tuple[str, AccountNature, str, int]] = [
    ("Capital Account", AccountNature.LIABILITY, "capital", 10),
    ("Current Liabilities", AccountNature.LIABILITY, "current_liability", 20),
    ("Sundry Creditors", AccountNature.LIABILITY, "payable", 21),
    ("Duties & Taxes", AccountNature.LIABILITY, "duties_taxes", 22),
    ("Loans (Liability)", AccountNature.LIABILITY, "current_liability", 25),
    ("Fixed Assets", AccountNature.ASSET, "fixed_asset", 40),
    ("Current Assets", AccountNature.ASSET, "current_asset", 50),
    ("Bank Accounts", AccountNature.ASSET, "bank", 51),
    ("Cash-in-hand", AccountNature.ASSET, "cash", 52),
    ("Sundry Debtors", AccountNature.ASSET, "receivable", 53),
    ("Sales Accounts", AccountNature.INCOME, "sales", 60),
    ("Direct Incomes", AccountNature.INCOME, "direct_income", 61),
    ("Indirect Incomes", AccountNature.INCOME, "indirect_income", 62),
    ("Purchase Accounts", AccountNature.EXPENSE, "purchase", 70),
    ("Direct Expenses", AccountNature.EXPENSE, "direct_expense", 71),
    ("Indirect Expenses", AccountNature.EXPENSE, "indirect_expense", 72),
]

# ledger name, group name
_DEFAULT_LEDGERS: list[tuple[str, str]] = [
    ("Cash", "Cash-in-hand"),
    ("Bank Account", "Bank Accounts"),
    ("Sales", "Sales Accounts"),
    ("Purchase", "Purchase Accounts"),
    ("Output CGST", "Duties & Taxes"),
    ("Output SGST", "Duties & Taxes"),
    ("Output IGST", "Duties & Taxes"),
    ("Output CESS", "Duties & Taxes"),
    ("Input CGST", "Duties & Taxes"),
    ("Input SGST", "Duties & Taxes"),
    ("Input IGST", "Duties & Taxes"),
    ("Input CESS", "Duties & Taxes"),
    ("Round Off", "Indirect Expenses"),
    ("Opening Balance Equity", "Capital Account"),
]


def current_fy_range(today: date | None = None) -> tuple[str, str]:
    """Indian financial year (1 Apr – 31 Mar) containing `today`."""
    today = today or date.today()
    start_year = today.year if today.month >= 4 else today.year - 1
    return f"{start_year}-04-01", f"{start_year + 1}-03-31"


@dataclass
class EntryDraft:
    ledger_id: uuid.UUID
    side: BalanceSide
    amount: Decimal
    narration: str | None = None


class AccountingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Chart of accounts
    # ------------------------------------------------------------------ #

    async def ensure_chart_of_accounts(self, organization_id: uuid.UUID) -> None:
        existing_groups = {
            g.name: g
            for g in (
                await self.session.execute(
                    select(LedgerGroup).where(LedgerGroup.organization_id == organization_id)
                )
            )
            .scalars()
            .all()
        }
        for name, nature, classification, sort_order in _DEFAULT_GROUPS:
            if name in existing_groups:
                continue
            group = LedgerGroup(
                organization_id=organization_id,
                name=name,
                nature=nature,
                classification=classification,
                is_system=True,
                sort_order=sort_order,
            )
            self.session.add(group)
            existing_groups[name] = group
        await self.session.flush()

        existing_ledgers = {
            lg.name
            for lg in (
                await self.session.execute(
                    select(Ledger).where(Ledger.organization_id == organization_id)
                )
            )
            .scalars()
            .all()
        }
        for name, group_name in _DEFAULT_LEDGERS:
            if name in existing_ledgers:
                continue
            self.session.add(
                Ledger(
                    organization_id=organization_id,
                    name=name,
                    group_id=existing_groups[group_name].id,
                    is_system=True,
                )
            )
        await self.session.flush()

    async def list_groups(self, organization_id: uuid.UUID) -> list[LedgerGroup]:
        result = await self.session.execute(
            select(LedgerGroup)
            .where(LedgerGroup.organization_id == organization_id)
            .order_by(LedgerGroup.sort_order, LedgerGroup.name)
        )
        return list(result.scalars().all())

    async def list_ledgers(self, organization_id: uuid.UUID) -> list[Ledger]:
        result = await self.session.execute(
            select(Ledger)
            .where(Ledger.organization_id == organization_id)
            .options(selectinload(Ledger.group))
            .order_by(Ledger.name)
        )
        return list(result.scalars().all())

    async def get_ledger(self, *, organization_id: uuid.UUID, ledger_id: uuid.UUID) -> Ledger:
        result = await self.session.execute(
            select(Ledger)
            .where(Ledger.id == ledger_id, Ledger.organization_id == organization_id)
            .options(selectinload(Ledger.group))
        )
        ledger = result.scalar_one_or_none()
        if ledger is None:
            raise NotFoundError("Ledger not found.")
        return ledger

    async def create_ledger(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        group_id: uuid.UUID,
        opening_balance: Decimal = Decimal("0"),
        opening_side: BalanceSide = BalanceSide.DEBIT,
        gstin: str | None = None,
        notes: str | None = None,
    ) -> Ledger:
        group = await self.session.get(LedgerGroup, group_id)
        if group is None or group.organization_id != organization_id:
            raise ValidationFailedError("Unknown ledger group.")
        dupe = await self.session.execute(
            select(Ledger).where(
                Ledger.organization_id == organization_id, func.lower(Ledger.name) == name.lower()
            )
        )
        if dupe.scalar_one_or_none() is not None:
            raise ConflictError(f"A ledger named '{name}' already exists.")

        ledger = Ledger(
            organization_id=organization_id,
            name=name.strip(),
            group_id=group_id,
            opening_balance=opening_balance,
            opening_side=opening_side,
            gstin=gstin,
            notes=notes,
        )
        self.session.add(ledger)
        await self.session.flush()
        await self.session.refresh(ledger, attribute_names=["group"])
        return ledger

    async def _get_or_create_party_ledger(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        group_classification: str,
        party_type: str | None,
        party_id: uuid.UUID | None,
        gstin: str | None,
    ) -> Ledger:
        clean = (name or "Unknown Party").strip()[:200]
        existing = await self.session.execute(
            select(Ledger).where(
                Ledger.organization_id == organization_id,
                func.lower(Ledger.name) == clean.lower(),
            )
        )
        ledger = existing.scalar_one_or_none()
        if ledger is not None:
            return ledger

        group = await self.session.execute(
            select(LedgerGroup).where(
                LedgerGroup.organization_id == organization_id,
                LedgerGroup.classification == group_classification,
            )
        )
        group_row = group.scalars().first()
        if group_row is None:
            raise ValidationFailedError(
                "Chart of accounts is not initialised for this organization."
            )
        ledger = Ledger(
            organization_id=organization_id,
            name=clean,
            group_id=group_row.id,
            gstin=gstin,
            party_type=party_type,
            party_id=party_id,
        )
        self.session.add(ledger)
        await self.session.flush()
        return ledger

    # ------------------------------------------------------------------ #
    # Vouchers
    # ------------------------------------------------------------------ #

    async def _next_voucher_number(
        self, *, organization_id: uuid.UUID, voucher_type: VoucherType
    ) -> str:
        count = (
            await self.session.execute(
                select(func.count())
                .select_from(Voucher)
                .where(
                    Voucher.organization_id == organization_id,
                    Voucher.voucher_type == voucher_type,
                )
            )
        ).scalar_one()
        return f"{_VOUCHER_PREFIX[voucher_type]}-{count + 1:04d}"

    async def create_voucher(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        voucher_type: VoucherType,
        voucher_date: str,
        entries: list[EntryDraft],
        narration: str | None = None,
        reference: str | None = None,
        source_invoice_id: uuid.UUID | None = None,
        is_auto_generated: bool = False,
    ) -> Voucher:
        engine.validate_balanced(
            [engine.EntryInput(engine.Side(e.side.value), e.amount) for e in entries]
        )

        ledger_ids = {e.ledger_id for e in entries}
        owned = (
            await self.session.execute(
                select(Ledger.id).where(
                    Ledger.organization_id == organization_id, Ledger.id.in_(ledger_ids)
                )
            )
        ).scalars().all()
        if set(owned) != ledger_ids:
            raise ValidationFailedError("One or more ledgers do not belong to this organization.")

        number = await self._next_voucher_number(
            organization_id=organization_id, voucher_type=voucher_type
        )
        total = sum(
            (e.amount for e in entries if e.side == BalanceSide.DEBIT), Decimal("0")
        )
        voucher = Voucher(
            organization_id=organization_id,
            voucher_type=voucher_type,
            voucher_number=number,
            date=voucher_date,
            narration=narration,
            reference=reference,
            total_amount=total,
            source_invoice_id=source_invoice_id,
            is_auto_generated=is_auto_generated,
            created_by=user_id,
        )
        voucher.entries = [
            VoucherEntry(
                ledger_id=e.ledger_id,
                side=e.side,
                amount=e.amount,
                narration=e.narration,
                sort_order=i,
            )
            for i, e in enumerate(entries)
        ]
        self.session.add(voucher)
        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="accounting.voucher.create",
                entity_type="voucher",
                entity_id=number,
                metadata_json={"type": voucher_type.value, "amount": str(total)},
            )
        )
        await self.session.flush()
        return voucher

    async def list_vouchers(
        self,
        *,
        organization_id: uuid.UUID,
        voucher_type: VoucherType | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 200,
    ) -> list[Voucher]:
        stmt = (
            select(Voucher)
            .where(Voucher.organization_id == organization_id)
            .options(selectinload(Voucher.entries))
        )
        if voucher_type is not None:
            stmt = stmt.where(Voucher.voucher_type == voucher_type)
        if date_from:
            stmt = stmt.where(Voucher.date >= date_from)
        if date_to:
            stmt = stmt.where(Voucher.date <= date_to)
        stmt = stmt.order_by(Voucher.date.desc(), Voucher.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_voucher(
        self, *, organization_id: uuid.UUID, voucher_id: uuid.UUID
    ) -> Voucher:
        result = await self.session.execute(
            select(Voucher)
            .where(Voucher.id == voucher_id, Voucher.organization_id == organization_id)
            .options(selectinload(Voucher.entries))
        )
        voucher = result.scalar_one_or_none()
        if voucher is None:
            raise NotFoundError("Voucher not found.")
        return voucher

    async def _ledger_by_name(self, organization_id: uuid.UUID, name: str) -> Ledger:
        result = await self.session.execute(
            select(Ledger).where(
                Ledger.organization_id == organization_id, Ledger.name == name
            )
        )
        ledger = result.scalar_one_or_none()
        if ledger is None:
            raise ValidationFailedError(
                f"System ledger '{name}' is missing — re-initialise the chart of accounts."
            )
        return ledger

    async def post_invoice(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID, invoice: Invoice
    ) -> Voucher:
        await self.ensure_chart_of_accounts(organization_id)

        existing = await self.session.execute(
            select(Voucher).where(
                Voucher.organization_id == organization_id,
                Voucher.source_invoice_id == invoice.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("This invoice has already been posted to the books.")

        items = invoice.items or []
        taxable = sum((i.taxable_value or Decimal("0") for i in items), Decimal("0"))
        cgst = sum((i.cgst or Decimal("0") for i in items), Decimal("0"))
        sgst = sum((i.sgst or Decimal("0") for i in items), Decimal("0"))
        igst = sum((i.igst or Decimal("0") for i in items), Decimal("0"))
        cess = sum((i.cess or Decimal("0") for i in items), Decimal("0"))
        if taxable <= 0:
            raise ValidationFailedError(
                "Invoice has no extracted taxable value to post."
            )
        total = taxable + cgst + sgst + igst + cess
        is_sales = invoice.direction == InvoiceDirection.SALES
        voucher_date = invoice.invoice_date or date.today().isoformat()

        party = await self._get_or_create_party_ledger(
            organization_id=organization_id,
            name=(invoice.buyer_name if is_sales else invoice.supplier_name) or "Unknown Party",
            group_classification="receivable" if is_sales else "payable",
            party_type="customer" if is_sales else "vendor",
            party_id=invoice.customer_id if is_sales else invoice.vendor_id,
            gstin=invoice.buyer_gstin if is_sales else invoice.supplier_gstin,
        )
        prefix = "Output" if is_sales else "Input"
        base_ledger = await self._ledger_by_name(
            organization_id, "Sales" if is_sales else "Purchase"
        )
        tax_map = [
            (f"{prefix} CGST", cgst),
            (f"{prefix} SGST", sgst),
            (f"{prefix} IGST", igst),
            (f"{prefix} CESS", cess),
        ]

        entries: list[EntryDraft] = []
        party_side = BalanceSide.DEBIT if is_sales else BalanceSide.CREDIT
        leg_side = BalanceSide.CREDIT if is_sales else BalanceSide.DEBIT

        entries.append(EntryDraft(party.id, party_side, total, "Being invoice booked"))
        entries.append(EntryDraft(base_ledger.id, leg_side, taxable))
        for ledger_name, amount in tax_map:
            if amount and amount > 0:
                tax_ledger = await self._ledger_by_name(organization_id, ledger_name)
                entries.append(EntryDraft(tax_ledger.id, leg_side, amount))

        return await self.create_voucher(
            organization_id=organization_id,
            user_id=user_id,
            voucher_type=VoucherType.SALES if is_sales else VoucherType.PURCHASE,
            voucher_date=voucher_date,
            entries=entries,
            narration=(
                f"{'Sales' if is_sales else 'Purchase'} invoice "
                f"{invoice.invoice_number or invoice.id} — {party.name}"
            ),
            reference=invoice.invoice_number,
            source_invoice_id=invoice.id,
            is_auto_generated=True,
        )

    # ------------------------------------------------------------------ #
    # Reports
    # ------------------------------------------------------------------ #

    async def _ledger_lines(
        self,
        *,
        organization_id: uuid.UUID,
        date_from: str,
        date_to: str,
        include_opening: bool = True,
    ) -> list[engine.LedgerLine]:
        ledgers = await self.list_ledgers(organization_id)
        by_id = {lg.id: lg for lg in ledgers}

        opening_rows = (
            await self.session.execute(
                select(VoucherEntry.ledger_id, VoucherEntry.side, func.sum(VoucherEntry.amount))
                .join(Voucher, VoucherEntry.voucher_id == Voucher.id)
                .where(Voucher.organization_id == organization_id, Voucher.date < date_from)
                .group_by(VoucherEntry.ledger_id, VoucherEntry.side)
            )
        ).all()
        period_rows = (
            await self.session.execute(
                select(VoucherEntry.ledger_id, VoucherEntry.side, func.sum(VoucherEntry.amount))
                .join(Voucher, VoucherEntry.voucher_id == Voucher.id)
                .where(
                    Voucher.organization_id == organization_id,
                    Voucher.date >= date_from,
                    Voucher.date <= date_to,
                )
                .group_by(VoucherEntry.ledger_id, VoucherEntry.side)
            )
        ).all()

        opening_by_ledger: dict[uuid.UUID, Decimal] = {}
        for ledger_id, side, amount in opening_rows:
            delta = amount if side == BalanceSide.DEBIT else -amount
            opening_by_ledger[ledger_id] = opening_by_ledger.get(ledger_id, Decimal("0")) + delta

        period_by_ledger: dict[uuid.UUID, list[Decimal]] = {}
        for ledger_id, side, amount in period_rows:
            slot = period_by_ledger.setdefault(ledger_id, [Decimal("0"), Decimal("0")])
            if side == BalanceSide.DEBIT:
                slot[0] += amount
            else:
                slot[1] += amount

        lines: list[engine.LedgerLine] = []
        for ledger in ledgers:
            manual_opening = (
                engine.opening_net(
                    ledger.opening_balance or Decimal("0"),
                    engine.Side(ledger.opening_side.value),
                )
                if include_opening
                else Decimal("0")
            )
            txn_opening = (
                opening_by_ledger.get(ledger.id, Decimal("0"))
                if include_opening
                else Decimal("0")
            )
            dr, cr = period_by_ledger.get(ledger.id, [Decimal("0"), Decimal("0")])
            lines.append(
                engine.LedgerLine(
                    ledger_id=str(ledger.id),
                    name=ledger.name,
                    group_name=by_id[ledger.id].group.name if by_id[ledger.id].group else "",
                    nature=engine.Nature(ledger.group.nature.value),
                    classification=ledger.group.classification or "",
                    opening_net=manual_opening + txn_opening,
                    debit_total=dr,
                    credit_total=cr,
                )
            )
        return lines

    async def trial_balance(
        self, *, organization_id: uuid.UUID, as_on: str | None = None
    ) -> dict:
        as_on = as_on or date.today().isoformat()
        lines = await self._ledger_lines(
            organization_id=organization_id, date_from=_EPOCH, date_to=as_on
        )
        tb = engine.trial_balance(lines)
        return {"as_on": as_on, **tb.as_dict()}

    async def profit_and_loss(
        self,
        *,
        organization_id: uuid.UUID,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        fy_from, fy_to = current_fy_range()
        date_from = date_from or fy_from
        date_to = date_to or fy_to
        lines = await self._ledger_lines(
            organization_id=organization_id,
            date_from=date_from,
            date_to=date_to,
            include_opening=False,
        )
        pnl = engine.profit_and_loss(lines)
        return {"date_from": date_from, "date_to": date_to, **pnl.as_dict()}

    async def balance_sheet(
        self, *, organization_id: uuid.UUID, as_on: str | None = None
    ) -> dict:
        as_on = as_on or date.today().isoformat()
        fy_from, _ = current_fy_range()
        pnl_lines = await self._ledger_lines(
            organization_id=organization_id,
            date_from=fy_from,
            date_to=as_on,
            include_opening=False,
        )
        net_profit = engine.profit_and_loss(pnl_lines).net_profit

        bs_lines = await self._ledger_lines(
            organization_id=organization_id, date_from=_EPOCH, date_to=as_on
        )
        bs = engine.balance_sheet(bs_lines, net_profit)
        return {"as_on": as_on, **bs.as_dict()}

    async def day_book(
        self,
        *,
        organization_id: uuid.UUID,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[Voucher]:
        return await self.list_vouchers(
            organization_id=organization_id, date_from=date_from, date_to=date_to
        )

    async def ledger_statement(
        self,
        *,
        organization_id: uuid.UUID,
        ledger_id: uuid.UUID,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        ledger = await self.get_ledger(organization_id=organization_id, ledger_id=ledger_id)
        date_from = date_from or current_fy_range()[0]
        date_to = date_to or _FAR_FUTURE

        opening_delta = (
            await self.session.execute(
                select(VoucherEntry.side, func.sum(VoucherEntry.amount))
                .join(Voucher, VoucherEntry.voucher_id == Voucher.id)
                .where(
                    Voucher.organization_id == organization_id,
                    VoucherEntry.ledger_id == ledger_id,
                    Voucher.date < date_from,
                )
                .group_by(VoucherEntry.side)
            )
        ).all()
        opening_net = engine.opening_net(
            ledger.opening_balance or Decimal("0"), engine.Side(ledger.opening_side.value)
        )
        for side, amount in opening_delta:
            opening_net += amount if side == BalanceSide.DEBIT else -amount

        rows = (
            await self.session.execute(
                select(Voucher, VoucherEntry)
                .join(VoucherEntry, VoucherEntry.voucher_id == Voucher.id)
                .where(
                    Voucher.organization_id == organization_id,
                    VoucherEntry.ledger_id == ledger_id,
                    Voucher.date >= date_from,
                    Voucher.date <= date_to,
                )
                .order_by(Voucher.date, Voucher.created_at)
            )
        ).all()
        txns = [
            engine.LedgerTxn(
                date=v.date,
                voucher_type=v.voucher_type.value,
                voucher_number=v.voucher_number,
                narration=e.narration or v.narration,
                debit=e.amount if e.side == BalanceSide.DEBIT else Decimal("0"),
                credit=e.amount if e.side == BalanceSide.CREDIT else Decimal("0"),
            )
            for v, e in rows
        ]
        statement = engine.ledger_statement(ledger.name, opening_net, txns)
        return {
            "ledger_id": str(ledger.id),
            "date_from": date_from,
            "date_to": date_to,
            **statement.as_dict(),
        }

    async def outstanding(self, *, organization_id: uuid.UUID, kind: str) -> dict:
        classification = "receivable" if kind == "receivable" else "payable"
        lines = await self._ledger_lines(
            organization_id=organization_id, date_from=_EPOCH, date_to=_FAR_FUTURE
        )
        rows = []
        total = Decimal("0")
        for line in lines:
            if line.classification != classification:
                continue
            balance = line.debit_balance if kind == "receivable" else line.credit_balance
            if balance <= 0:
                continue
            rows.append({"ledger_id": line.ledger_id, "name": line.name, "balance": str(balance)})
            total += balance
        rows.sort(key=lambda r: Decimal(r["balance"]), reverse=True)
        return {"kind": kind, "rows": rows, "total": str(total)}

    # ------------------------------------------------------------------ #
    # CSV export ("financial generator")
    # ------------------------------------------------------------------ #

    @staticmethod
    def report_to_csv(report_type: str, payload: dict) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        if report_type == "trial-balance":
            w.writerow(["Ledger", "Group", "Debit", "Credit"])
            for r in payload["rows"]:
                w.writerow([r["name"], r["group_name"], r["debit"], r["credit"]])
            w.writerow(["TOTAL", "", payload["total_debit"], payload["total_credit"]])
        elif report_type == "profit-loss":
            w.writerow(["Section", "Ledger", "Group", "Amount"])
            for section in (
                "direct_income",
                "direct_expense",
                "indirect_income",
                "indirect_expense",
            ):
                for r in payload[section]:
                    w.writerow([section, r["name"], r["group_name"], r["amount"]])
            w.writerow(["", "", "Gross Profit", payload["gross_profit"]])
            w.writerow(["", "", "Net Profit", payload["net_profit"]])
        elif report_type == "balance-sheet":
            w.writerow(["Side", "Ledger", "Group", "Amount"])
            for r in payload["liabilities"]:
                w.writerow(["Liabilities", r["name"], r["group_name"], r["amount"]])
            w.writerow(["Liabilities", "Net Profit", "Profit & Loss A/c", payload["net_profit"]])
            for r in payload["assets"]:
                w.writerow(["Assets", r["name"], r["group_name"], r["amount"]])
            w.writerow(["", "", "Total Liabilities", payload["total_liabilities"]])
            w.writerow(["", "", "Total Assets", payload["total_assets"]])
        else:
            raise ValidationFailedError(f"Unknown report type: {report_type}")
        return buf.getvalue()
