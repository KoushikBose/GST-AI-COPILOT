"""Unit tests for the deterministic double-entry accounting engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import ValidationFailedError
from app.rules.accounting import (
    EntryInput,
    LedgerLine,
    LedgerTxn,
    Nature,
    Side,
    balance_sheet,
    ledger_statement,
    opening_net,
    profit_and_loss,
    trial_balance,
    validate_balanced,
)

D = Decimal


def _line(name, nature, classification, *, opening=("0", "dr"), dr="0", cr="0"):
    amt, side = opening
    return LedgerLine(
        ledger_id=name,
        name=name,
        group_name=classification,
        nature=nature,
        classification=classification,
        opening_net=opening_net(D(amt), Side(side)),
        debit_total=D(dr),
        credit_total=D(cr),
    )


def test_validate_balanced_accepts_a_balanced_voucher():
    validate_balanced(
        [
            EntryInput(Side.DEBIT, D("118")),
            EntryInput(Side.CREDIT, D("100")),
            EntryInput(Side.CREDIT, D("18")),
        ]
    )


def test_validate_balanced_rejects_unbalanced():
    with pytest.raises(ValidationFailedError):
        validate_balanced([EntryInput(Side.DEBIT, D("100")), EntryInput(Side.CREDIT, D("90"))])


def test_validate_balanced_rejects_single_entry_and_nonpositive():
    with pytest.raises(ValidationFailedError):
        validate_balanced([EntryInput(Side.DEBIT, D("100"))])
    with pytest.raises(ValidationFailedError):
        validate_balanced([EntryInput(Side.DEBIT, D("0")), EntryInput(Side.CREDIT, D("0"))])


def test_trial_balance_ties_out():
    lines = [
        _line("Sundry Debtors", Nature.ASSET, "receivable", dr="118"),
        _line("Sales", Nature.INCOME, "sales", cr="100"),
        _line("Output CGST", Nature.LIABILITY, "duties_taxes", cr="9"),
        _line("Output SGST", Nature.LIABILITY, "duties_taxes", cr="9"),
    ]
    tb = trial_balance(lines)
    assert tb.total_debit == D("118")
    assert tb.total_credit == D("118")
    assert tb.is_balanced


def test_profit_and_loss_gross_and_net():
    lines = [
        _line("Sales", Nature.INCOME, "sales", cr="100000"),
        _line("Purchase", Nature.EXPENSE, "purchase", dr="60000"),
        _line("Rent", Nature.EXPENSE, "indirect_expense", dr="10000"),
        _line("Interest Received", Nature.INCOME, "indirect_income", cr="2000"),
    ]
    pnl = profit_and_loss(lines)
    assert pnl.gross_profit == D("40000")  # 100000 - 60000
    assert pnl.net_profit == D("32000")  # 40000 + 2000 - 10000


def test_balance_sheet_balances_with_net_profit():
    # Capital 50000 (cr), Bank 82000 (dr), Debtors 0, Creditors 0,
    # net profit 32000 → Assets 82000 == Liabilities 50000 + 32000
    lines = [
        _line("Capital", Nature.LIABILITY, "capital", opening=("50000", "cr")),
        _line("Bank", Nature.ASSET, "bank", dr="82000"),
    ]
    bs = balance_sheet(lines, net_profit=D("32000"))
    assert bs.total_assets == D("82000")
    assert bs.total_liabilities == D("82000")
    assert bs.is_balanced


def test_current_fy_range_indian_financial_year():
    from datetime import date

    from app.services.accounting_service import current_fy_range

    assert current_fy_range(date(2026, 1, 15)) == ("2025-04-01", "2026-03-31")
    assert current_fy_range(date(2026, 5, 1)) == ("2026-04-01", "2027-03-31")


def test_report_to_csv_trial_balance_shape():
    from app.services.accounting_service import AccountingService

    csv_text = AccountingService.report_to_csv(
        "trial-balance",
        {
            "rows": [{"name": "Cash", "group_name": "Cash-in-hand", "debit": "100", "credit": "0"}],
            "total_debit": "100",
            "total_credit": "100",
        },
    )
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Ledger,Group,Debit,Credit"
    assert lines[-1] == "TOTAL,,100,100"


def test_ledger_statement_running_balance():
    txns = [
        LedgerTxn("2026-04-02", "sales", "SAL-0001", "Inv 1", D("1180"), D("0")),
        LedgerTxn("2026-04-05", "receipt", "RCT-0001", "Payment", D("0"), D("1000")),
    ]
    stmt = ledger_statement("Acme Traders", opening_net_value=D("0"), txns=txns)
    assert stmt.txns[0].running_net == D("1180")
    assert stmt.txns[1].running_net == D("180")
    assert stmt.as_dict()["closing_side"] == "dr"
