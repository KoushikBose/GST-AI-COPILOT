"""Unit tests for the deterministic GST rule engine.

These tests require no database, no LLM, and no network — they are the
fastest signal that the tax-arithmetic core is correct.
"""

from decimal import Decimal

import pytest

from app.core.errors import ValidationFailedError
from app.rules.gst_calculator import GSTCalculator, TransactionType


@pytest.fixture
def calculator() -> GSTCalculator:
    return GSTCalculator(rules_version="2026.01")


class TestIntraStateCalculation:
    def test_18_percent_splits_evenly_into_cgst_sgst(self, calculator: GSTCalculator) -> None:
        result = calculator.calculate(
            taxable_value=Decimal("100000"),
            gst_rate=Decimal("18"),
            transaction_type=TransactionType.INTRA_STATE,
        )
        assert result.cgst == Decimal("9000.00")
        assert result.sgst == Decimal("9000.00")
        assert result.igst == Decimal("0.00")
        assert result.total_tax == Decimal("18000.00")
        assert result.grand_total == Decimal("118000.00")

    def test_odd_rate_rounds_half_up(self, calculator: GSTCalculator) -> None:
        # 100 * 2.5% = 2.50 exactly on each side for a 5% rate — use a rate
        # that forces a genuine rounding decision instead.
        result = calculator.calculate(
            taxable_value=Decimal("33.33"),
            gst_rate=Decimal("18"),
            transaction_type=TransactionType.INTRA_STATE,
        )
        # 33.33 * 9% = 2.9997 -> rounds to 3.00
        assert result.cgst == Decimal("3.00")
        assert result.sgst == Decimal("3.00")

    def test_zero_taxable_value(self, calculator: GSTCalculator) -> None:
        result = calculator.calculate(
            taxable_value=0, gst_rate=18, transaction_type=TransactionType.INTRA_STATE
        )
        assert result.grand_total == Decimal("0.00")


class TestInterStateCalculation:
    def test_igst_only(self, calculator: GSTCalculator) -> None:
        result = calculator.calculate(
            taxable_value=Decimal("100000"),
            gst_rate=Decimal("18"),
            transaction_type=TransactionType.INTER_STATE,
        )
        assert result.igst == Decimal("18000.00")
        assert result.cgst == Decimal("0.00")
        assert result.sgst == Decimal("0.00")
        assert result.grand_total == Decimal("118000.00")


class TestCess:
    def test_cess_applied_on_top_of_igst(self, calculator: GSTCalculator) -> None:
        result = calculator.calculate(
            taxable_value=Decimal("100000"),
            gst_rate=Decimal("28"),
            transaction_type=TransactionType.INTER_STATE,
            cess_rate=Decimal("12"),
        )
        assert result.igst == Decimal("28000.00")
        assert result.cess == Decimal("12000.00")
        assert result.total_tax == Decimal("40000.00")
        assert result.grand_total == Decimal("140000.00")


class TestZeroRatedTransactions:
    @pytest.mark.parametrize(
        "txn_type",
        [
            TransactionType.EXPORT,
            TransactionType.SEZ_SUPPLY,
            TransactionType.EXEMPT,
            TransactionType.NIL_RATED,
        ],
    )
    def test_zero_tax_regardless_of_rate(
        self, calculator: GSTCalculator, txn_type: TransactionType
    ) -> None:
        result = calculator.calculate(
            taxable_value=Decimal("50000"), gst_rate=Decimal("18"), transaction_type=txn_type
        )
        assert result.total_tax == Decimal("0.00")
        assert result.grand_total == Decimal("50000.00")
        assert len(result.warnings) == 1


class TestValidation:
    def test_negative_taxable_value_rejected(self, calculator: GSTCalculator) -> None:
        with pytest.raises(ValidationFailedError):
            calculator.calculate(
                taxable_value=Decimal("-1"),
                gst_rate=Decimal("18"),
                transaction_type=TransactionType.INTRA_STATE,
            )

    def test_rate_over_100_rejected(self, calculator: GSTCalculator) -> None:
        with pytest.raises(ValidationFailedError):
            calculator.calculate(
                taxable_value=Decimal("100"),
                gst_rate=Decimal("101"),
                transaction_type=TransactionType.INTRA_STATE,
            )

    def test_invalid_numeric_value_rejected(self, calculator: GSTCalculator) -> None:
        with pytest.raises(ValidationFailedError):
            calculator.calculate(
                taxable_value="not-a-number",
                gst_rate=Decimal("18"),
                transaction_type=TransactionType.INTRA_STATE,
            )


class TestLineItemAggregation:
    def test_multiple_line_items_sum_correctly(self, calculator: GSTCalculator) -> None:
        items = [
            {"taxable_value": "1000", "gst_rate": "18"},
            {"taxable_value": "2000", "gst_rate": "12"},
            {"taxable_value": "500", "gst_rate": "5"},
        ]
        line_results, total = calculator.calculate_line_items(
            items, transaction_type=TransactionType.INTRA_STATE
        )
        assert len(line_results) == 3
        assert total.taxable_value == Decimal("3500.00")
        # 1000*9%=90 cgst/sgst, 2000*6%=120, 500*2.5%=12.5
        assert total.cgst == Decimal("222.50")
        assert total.sgst == Decimal("222.50")
        assert total.grand_total == Decimal("3945.00")

    def test_empty_items_rejected(self, calculator: GSTCalculator) -> None:
        with pytest.raises(ValidationFailedError):
            calculator.calculate_line_items([], transaction_type=TransactionType.INTRA_STATE)
