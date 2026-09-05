"""Deterministic double-entry accounting engine.

Like every module under ``app/rules/``, this is LLM-free, DB-free and a pure
function of the data handed to it — so the bookkeeping invariants (every
voucher balances, the trial balance ties, Assets = Liabilities + Equity)
are unit-testable in isolation and reproducible.

Sign convention (Tally-style, group-agnostic):

    net = opening_net + Σ(debit amounts) − Σ(credit amounts)

    net > 0  → the ledger carries a DEBIT balance
    net < 0  → the ledger carries a CREDIT balance

The group's *nature* (asset / liability / income / expense) is only used to
place a ledger on the right statement, never to decide its balance side.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.core.errors import ValidationFailedError

_ZERO = Decimal("0.00")
_TOLERANCE = Decimal("0.01")


class Nature(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"


class Side(StrEnum):
    DEBIT = "dr"
    CREDIT = "cr"


@dataclass(frozen=True)
class EntryInput:
    side: Side
    amount: Decimal


def validate_balanced(entries: list[EntryInput]) -> None:
    """Raise unless the voucher has >= 2 entries that sum debit == credit."""
    if len(entries) < 2:
        raise ValidationFailedError("A voucher needs at least two entries.")
    debit = sum((e.amount for e in entries if e.side == Side.DEBIT), _ZERO)
    credit = sum((e.amount for e in entries if e.side == Side.CREDIT), _ZERO)
    if any(e.amount <= 0 for e in entries):
        raise ValidationFailedError("Every voucher entry amount must be positive.")
    if abs(debit - credit) > _TOLERANCE:
        raise ValidationFailedError(
            f"Voucher does not balance: debit ₹{debit} vs credit ₹{credit}."
        )


@dataclass
class LedgerLine:
    ledger_id: str
    name: str
    group_name: str
    nature: Nature
    classification: str
    opening_net: Decimal = _ZERO
    debit_total: Decimal = _ZERO
    credit_total: Decimal = _ZERO

    @property
    def closing_net(self) -> Decimal:
        return self.opening_net + self.debit_total - self.credit_total

    @property
    def debit_balance(self) -> Decimal:
        n = self.closing_net
        return n if n > 0 else _ZERO

    @property
    def credit_balance(self) -> Decimal:
        n = self.closing_net
        return -n if n < 0 else _ZERO


def opening_net(amount: Decimal, side: Side) -> Decimal:
    return amount if side == Side.DEBIT else -amount


# --------------------------------------------------------------------------- #
# Trial balance
# --------------------------------------------------------------------------- #


@dataclass
class TrialBalanceRow:
    ledger_id: str
    name: str
    group_name: str
    debit: Decimal
    credit: Decimal

    def as_dict(self) -> dict:
        return {
            "ledger_id": self.ledger_id,
            "name": self.name,
            "group_name": self.group_name,
            "debit": str(self.debit),
            "credit": str(self.credit),
        }


@dataclass
class TrialBalance:
    rows: list[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debit - self.total_credit) <= _TOLERANCE

    def as_dict(self) -> dict:
        return {
            "rows": [r.as_dict() for r in self.rows],
            "total_debit": str(self.total_debit),
            "total_credit": str(self.total_credit),
            "difference": str(self.total_debit - self.total_credit),
            "is_balanced": self.is_balanced,
        }


def trial_balance(lines: list[LedgerLine]) -> TrialBalance:
    rows: list[TrialBalanceRow] = []
    for line in sorted(lines, key=lambda x: (x.nature.value, x.group_name, x.name)):
        if line.debit_balance == _ZERO and line.credit_balance == _ZERO:
            continue
        rows.append(
            TrialBalanceRow(
                ledger_id=line.ledger_id,
                name=line.name,
                group_name=line.group_name,
                debit=line.debit_balance,
                credit=line.credit_balance,
            )
        )
    return TrialBalance(
        rows=rows,
        total_debit=sum((r.debit for r in rows), _ZERO),
        total_credit=sum((r.credit for r in rows), _ZERO),
    )


# --------------------------------------------------------------------------- #
# Profit & Loss
# --------------------------------------------------------------------------- #

_DIRECT_CLASSIFICATIONS = {"sales", "purchase", "direct_income", "direct_expense", "stock"}


@dataclass
class StatementLine:
    name: str
    group_name: str
    amount: Decimal

    def as_dict(self) -> dict:
        return {"name": self.name, "group_name": self.group_name, "amount": str(self.amount)}


@dataclass
class ProfitAndLoss:
    direct_income: list[StatementLine]
    direct_expense: list[StatementLine]
    indirect_income: list[StatementLine]
    indirect_expense: list[StatementLine]
    gross_profit: Decimal
    net_profit: Decimal

    def as_dict(self) -> dict:
        return {
            "direct_income": [x.as_dict() for x in self.direct_income],
            "direct_expense": [x.as_dict() for x in self.direct_expense],
            "indirect_income": [x.as_dict() for x in self.indirect_income],
            "indirect_expense": [x.as_dict() for x in self.indirect_expense],
            "total_direct_income": str(sum((x.amount for x in self.direct_income), _ZERO)),
            "total_direct_expense": str(sum((x.amount for x in self.direct_expense), _ZERO)),
            "total_indirect_income": str(sum((x.amount for x in self.indirect_income), _ZERO)),
            "total_indirect_expense": str(sum((x.amount for x in self.indirect_expense), _ZERO)),
            "gross_profit": str(self.gross_profit),
            "net_profit": str(self.net_profit),
        }


def _income_amount(line: LedgerLine) -> Decimal:
    # Income ledgers normally carry a credit balance; show it as a positive figure.
    return -line.closing_net


def _expense_amount(line: LedgerLine) -> Decimal:
    return line.closing_net


def profit_and_loss(lines: list[LedgerLine]) -> ProfitAndLoss:
    di: list[StatementLine] = []
    de: list[StatementLine] = []
    ii: list[StatementLine] = []
    ie: list[StatementLine] = []

    for line in lines:
        is_direct = line.classification in _DIRECT_CLASSIFICATIONS
        if line.nature == Nature.INCOME:
            amt = _income_amount(line)
            if amt == _ZERO:
                continue
            (di if is_direct else ii).append(StatementLine(line.name, line.group_name, amt))
        elif line.nature == Nature.EXPENSE:
            amt = _expense_amount(line)
            if amt == _ZERO:
                continue
            (de if is_direct else ie).append(StatementLine(line.name, line.group_name, amt))

    total_di = sum((x.amount for x in di), _ZERO)
    total_de = sum((x.amount for x in de), _ZERO)
    total_ii = sum((x.amount for x in ii), _ZERO)
    total_ie = sum((x.amount for x in ie), _ZERO)

    gross_profit = total_di - total_de
    net_profit = gross_profit + total_ii - total_ie
    return ProfitAndLoss(di, de, ii, ie, gross_profit, net_profit)


# --------------------------------------------------------------------------- #
# Balance sheet
# --------------------------------------------------------------------------- #


@dataclass
class BalanceSheet:
    assets: list[StatementLine]
    liabilities: list[StatementLine]
    net_profit: Decimal
    total_assets: Decimal
    total_liabilities: Decimal

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_assets - self.total_liabilities) <= _TOLERANCE

    def as_dict(self) -> dict:
        return {
            "assets": [x.as_dict() for x in self.assets],
            "liabilities": [x.as_dict() for x in self.liabilities],
            "net_profit": str(self.net_profit),
            "total_assets": str(self.total_assets),
            "total_liabilities": str(self.total_liabilities),
            "difference": str(self.total_assets - self.total_liabilities),
            "is_balanced": self.is_balanced,
        }


def balance_sheet(lines: list[LedgerLine], net_profit: Decimal) -> BalanceSheet:
    assets: list[StatementLine] = []
    liabilities: list[StatementLine] = []

    for line in lines:
        if line.nature == Nature.ASSET:
            amt = line.closing_net
            if amt != _ZERO:
                assets.append(StatementLine(line.name, line.group_name, amt))
        elif line.nature == Nature.LIABILITY:
            amt = -line.closing_net
            if amt != _ZERO:
                liabilities.append(StatementLine(line.name, line.group_name, amt))

    total_assets = sum((x.amount for x in assets), _ZERO)
    # Current-period profit accrues to the owners → liabilities/equity side.
    total_liabilities = sum((x.amount for x in liabilities), _ZERO) + net_profit

    return BalanceSheet(
        assets=assets,
        liabilities=liabilities,
        net_profit=net_profit,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
    )


# --------------------------------------------------------------------------- #
# Ledger statement (running balance)
# --------------------------------------------------------------------------- #


@dataclass
class LedgerTxn:
    date: str
    voucher_type: str
    voucher_number: str
    narration: str | None
    debit: Decimal
    credit: Decimal
    running_net: Decimal = _ZERO

    def as_dict(self) -> dict:
        net = self.running_net
        return {
            "date": self.date,
            "voucher_type": self.voucher_type,
            "voucher_number": self.voucher_number,
            "narration": self.narration,
            "debit": str(self.debit) if self.debit else "",
            "credit": str(self.credit) if self.credit else "",
            "balance": str(abs(net)),
            "balance_side": "dr" if net >= 0 else "cr",
        }


@dataclass
class LedgerStatement:
    ledger_name: str
    opening_net: Decimal
    txns: list[LedgerTxn]
    closing_net: Decimal = _ZERO

    def as_dict(self) -> dict:
        return {
            "ledger_name": self.ledger_name,
            "opening_balance": str(abs(self.opening_net)),
            "opening_side": "dr" if self.opening_net >= 0 else "cr",
            "closing_balance": str(abs(self.closing_net)),
            "closing_side": "dr" if self.closing_net >= 0 else "cr",
            "transactions": [t.as_dict() for t in self.txns],
        }


def ledger_statement(
    ledger_name: str, opening_net_value: Decimal, txns: list[LedgerTxn]
) -> LedgerStatement:
    running = opening_net_value
    for txn in txns:
        running = running + txn.debit - txn.credit
        txn.running_net = running
    return LedgerStatement(
        ledger_name=ledger_name,
        opening_net=opening_net_value,
        txns=txns,
        closing_net=running,
    )
