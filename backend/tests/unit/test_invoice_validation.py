"""Unit tests for the deterministic invoice validation rule engine."""

from decimal import Decimal

from app.models.invoice import TransactionScope
from app.rules.invoice_validation import (
    InvoiceLineItemInput,
    InvoiceValidationInput,
    validate_invoice,
)

_VALID_SUPPLIER_GSTIN = "27AAPFU0939F1ZV"
_VALID_BUYER_GSTIN = "29AABCU9603R1ZJ"  # structurally valid (verified checksum)


def _clean_invoice(**overrides) -> InvoiceValidationInput:
    defaults = dict(
        invoice_number="INV-2026-0001",
        invoice_date="2026-01-15",
        supplier_gstin=_VALID_SUPPLIER_GSTIN,
        buyer_gstin=_VALID_BUYER_GSTIN,
        place_of_supply="Maharashtra",
        transaction_scope=TransactionScope.INTRA_STATE,
        items=[
            InvoiceLineItemInput(
                description="Consulting services",
                hsn_sac="9983",
                taxable_value=Decimal("100000"),
                gst_rate=Decimal("18"),
                cgst=Decimal("9000"),
                sgst=Decimal("9000"),
            )
        ],
        declared_taxable_value=Decimal("100000"),
    )
    defaults.update(overrides)
    return InvoiceValidationInput(**defaults)


class TestCleanInvoicePasses:
    def test_fully_valid_invoice_passes_all_checks(self) -> None:
        report = validate_invoice(_clean_invoice())
        assert report.status == "PASSED"
        assert report.score == 100
        assert report.issues == []
        assert report.passed_checks == report.total_checks


class TestGSTINChecks:
    def test_missing_supplier_gstin_is_critical(self) -> None:
        report = validate_invoice(_clean_invoice(supplier_gstin=None))
        assert report.status == "FAILED"
        codes = [i.rule_code for i in report.issues]
        assert "GSTIN_MISSING" in codes

    def test_malformed_gstin_is_critical(self) -> None:
        report = validate_invoice(_clean_invoice(buyer_gstin="INVALID_GSTIN"))
        assert report.status == "FAILED"
        assert any(i.rule_code == "GSTIN_INVALID_FORMAT" for i in report.issues)


class TestInvoiceMetadataChecks:
    def test_missing_invoice_number_is_high_severity(self) -> None:
        report = validate_invoice(_clean_invoice(invoice_number=""))
        assert report.status == "WARNING"
        assert any(i.rule_code == "INVOICE_NUMBER_MISSING" for i in report.issues)

    def test_duplicate_invoice_number_flagged(self) -> None:
        report = validate_invoice(_clean_invoice(is_duplicate_invoice_number=True))
        assert any(i.rule_code == "DUPLICATE_INVOICE_NUMBER" for i in report.issues)

    def test_missing_date_is_medium_severity(self) -> None:
        report = validate_invoice(_clean_invoice(invoice_date=None))
        assert any(i.rule_code == "INVOICE_DATE_MISSING" for i in report.issues)

    def test_missing_place_of_supply_flagged(self) -> None:
        report = validate_invoice(_clean_invoice(place_of_supply=None))
        assert any(i.rule_code == "PLACE_OF_SUPPLY_MISSING" for i in report.issues)


class TestLineItemChecks:
    def test_no_line_items_is_critical(self) -> None:
        report = validate_invoice(_clean_invoice(items=[]))
        assert report.status == "FAILED"
        assert any(i.rule_code == "NO_LINE_ITEMS" for i in report.issues)

    def test_missing_hsn_sac_flagged(self) -> None:
        report = validate_invoice(
            _clean_invoice(
                items=[
                    InvoiceLineItemInput(
                        description="Goods",
                        hsn_sac=None,
                        taxable_value=Decimal("1000"),
                        gst_rate=Decimal("18"),
                        cgst=Decimal("90"),
                        sgst=Decimal("90"),
                    )
                ],
                declared_taxable_value=Decimal("1000"),
            )
        )
        assert any(i.rule_code == "HSN_SAC_MISSING" for i in report.issues)


class TestArithmeticChecks:
    def test_tax_mismatch_detected(self) -> None:
        report = validate_invoice(
            _clean_invoice(
                items=[
                    InvoiceLineItemInput(
                        description="Goods",
                        hsn_sac="1234",
                        taxable_value=Decimal("100000"),
                        gst_rate=Decimal("18"),
                        # Declared tax is wildly wrong for an 18% intra-state rate.
                        cgst=Decimal("1000"),
                        sgst=Decimal("1000"),
                    )
                ],
                declared_taxable_value=Decimal("100000"),
            )
        )
        assert any(i.rule_code == "TAX_ARITHMETIC_MISMATCH" for i in report.issues)

    def test_taxable_value_sum_mismatch_detected(self) -> None:
        report = validate_invoice(_clean_invoice(declared_taxable_value=Decimal("999999")))
        assert any(i.rule_code == "TAXABLE_VALUE_MISMATCH" for i in report.issues)

    def test_small_rounding_drift_is_tolerated(self) -> None:
        # ₹0.50 drift should not trip the arithmetic-mismatch rule.
        report = validate_invoice(
            _clean_invoice(
                items=[
                    InvoiceLineItemInput(
                        description="Consulting services",
                        hsn_sac="9983",
                        taxable_value=Decimal("100000"),
                        gst_rate=Decimal("18"),
                        cgst=Decimal("9000.25"),
                        sgst=Decimal("8999.75"),
                    )
                ],
                declared_taxable_value=Decimal("100000"),
            )
        )
        assert not any(i.rule_code == "TAX_ARITHMETIC_MISMATCH" for i in report.issues)


class TestScoring:
    def test_score_decreases_with_more_issues(self) -> None:
        clean_report = validate_invoice(_clean_invoice())
        broken_report = validate_invoice(
            _clean_invoice(supplier_gstin=None, invoice_number=None, invoice_date=None)
        )
        assert broken_report.score < clean_report.score

    def test_score_never_goes_below_zero(self) -> None:
        report = validate_invoice(
            _clean_invoice(
                supplier_gstin=None,
                buyer_gstin=None,
                invoice_number=None,
                invoice_date=None,
                place_of_supply=None,
                items=[],
            )
        )
        assert report.score == 0
