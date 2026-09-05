"""Deterministic invoice validation rules.

Every check here is a plain function of invoice data — no LLM, no network
call — so the whole rule set is unit-testable in isolation and its output
is reproducible given the same input. The Compliance Agent (Phase 9)
wraps this to add AI *explanation* of what these issues mean; it never
re-decides what counts as an issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.models.invoice import TransactionScope
from app.rules.gst_calculator import GSTCalculator, TransactionType
from app.rules.gstin_validator import validate_gstin


class IssueSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ValidationIssue:
    rule_code: str
    severity: IssueSeverity
    field: str | None
    message: str
    recommendation: str | None = None


@dataclass
class InvoiceLineItemInput:
    description: str | None
    hsn_sac: str | None
    taxable_value: Decimal
    gst_rate: Decimal
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")


@dataclass
class InvoiceValidationInput:
    invoice_number: str | None
    invoice_date: str | None
    supplier_gstin: str | None
    buyer_gstin: str | None
    place_of_supply: str | None
    transaction_scope: TransactionScope | None = None
    items: list[InvoiceLineItemInput] = field(default_factory=list)
    declared_taxable_value: Decimal | None = None
    declared_total_tax: Decimal | None = None
    declared_grand_total: Decimal | None = None
    is_duplicate_invoice_number: bool = False


@dataclass
class ValidationReport:
    status: str  # "PASSED" | "WARNING" | "FAILED"
    score: int  # 0-100
    passed_checks: int
    total_checks: int
    issues: list[ValidationIssue]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "score": self.score,
            "passed_checks": self.passed_checks,
            "total_checks": self.total_checks,
            "issues": [
                {
                    "rule_code": i.rule_code,
                    "severity": i.severity.value,
                    "field": i.field,
                    "message": i.message,
                    "recommendation": i.recommendation,
                }
                for i in self.issues
            ],
        }


_SEVERITY_PENALTY = {
    IssueSeverity.CRITICAL: 30,
    IssueSeverity.HIGH: 15,
    IssueSeverity.MEDIUM: 8,
    IssueSeverity.LOW: 3,
    IssueSeverity.INFO: 0,
}

_TOLERANCE = Decimal("1.00")  # allow up to ₹1 arithmetic drift from rounding


def _rule_gstin_present_and_valid(
    inv: InvoiceValidationInput, field_name: str, gstin: str | None, issues: list[ValidationIssue]
) -> bool:
    if not gstin:
        issues.append(
            ValidationIssue(
                rule_code="GSTIN_MISSING",
                severity=IssueSeverity.CRITICAL,
                field=field_name,
                message=f"{field_name} is missing from the invoice.",
                recommendation="Request a corrected invoice with the GSTIN included.",
            )
        )
        return False

    result = validate_gstin(gstin)
    if not result.is_valid:
        issues.append(
            ValidationIssue(
                rule_code="GSTIN_INVALID_FORMAT",
                severity=IssueSeverity.CRITICAL,
                field=field_name,
                message=f"{field_name} '{gstin}' is not a validly formatted GSTIN: "
                f"{'; '.join(result.errors)}",
                recommendation="Verify the GSTIN with the counterparty.",
            )
        )
        return False
    return True


def _rule_invoice_number_present(
    inv: InvoiceValidationInput, issues: list[ValidationIssue]
) -> bool:
    if not inv.invoice_number or not inv.invoice_number.strip():
        issues.append(
            ValidationIssue(
                rule_code="INVOICE_NUMBER_MISSING",
                severity=IssueSeverity.HIGH,
                field="invoice_number",
                message="Invoice number is missing.",
            )
        )
        return False
    return True


def _rule_no_duplicate_invoice_number(
    inv: InvoiceValidationInput, issues: list[ValidationIssue]
) -> bool:
    if inv.is_duplicate_invoice_number:
        issues.append(
            ValidationIssue(
                rule_code="DUPLICATE_INVOICE_NUMBER",
                severity=IssueSeverity.HIGH,
                field="invoice_number",
                message=(
                    f"Invoice number '{inv.invoice_number}' has already been "
                    "recorded for this supplier."
                ),
                recommendation="Confirm this is not a duplicate submission before proceeding.",
            )
        )
        return False
    return True


def _rule_invoice_date_present(inv: InvoiceValidationInput, issues: list[ValidationIssue]) -> bool:
    if not inv.invoice_date:
        issues.append(
            ValidationIssue(
                rule_code="INVOICE_DATE_MISSING",
                severity=IssueSeverity.MEDIUM,
                field="invoice_date",
                message="Invoice date is missing.",
            )
        )
        return False
    return True


def _rule_place_of_supply_present(
    inv: InvoiceValidationInput, issues: list[ValidationIssue]
) -> bool:
    if not inv.place_of_supply:
        issues.append(
            ValidationIssue(
                rule_code="PLACE_OF_SUPPLY_MISSING",
                severity=IssueSeverity.MEDIUM,
                field="place_of_supply",
                message="Place of supply is missing, which is required to determine "
                "CGST/SGST vs. IGST applicability.",
            )
        )
        return False
    return True


def _rule_line_items_present(inv: InvoiceValidationInput, issues: list[ValidationIssue]) -> bool:
    if not inv.items:
        issues.append(
            ValidationIssue(
                rule_code="NO_LINE_ITEMS",
                severity=IssueSeverity.CRITICAL,
                field="items",
                message="No line items were extracted from this invoice.",
            )
        )
        return False
    return True


def _rule_hsn_sac_present(inv: InvoiceValidationInput, issues: list[ValidationIssue]) -> bool:
    missing = [i for i, item in enumerate(inv.items, start=1) if not item.hsn_sac]
    if missing:
        issues.append(
            ValidationIssue(
                rule_code="HSN_SAC_MISSING",
                severity=IssueSeverity.MEDIUM,
                field="items.hsn_sac",
                message=f"HSN/SAC code missing on line item(s): {', '.join(map(str, missing))}.",
                recommendation=(
                    "HSN/SAC is mandatory for GST-compliant invoices above the threshold."
                ),
            )
        )
        return False
    return True


def _rule_tax_arithmetic_matches_declared_rate(
    inv: InvoiceValidationInput, issues: list[ValidationIssue]
) -> bool:
    if not inv.items or inv.transaction_scope is None:
        return True

    calculator = GSTCalculator()
    txn_type = TransactionType(inv.transaction_scope.value)
    all_ok = True

    for idx, item in enumerate(inv.items, start=1):
        try:
            expected = calculator.calculate(
                taxable_value=item.taxable_value,
                gst_rate=item.gst_rate,
                transaction_type=txn_type,
            )
        except Exception:
            continue

        actual_total = item.cgst + item.sgst + item.igst
        expected_total = expected.cgst + expected.sgst + expected.igst
        if abs(actual_total - expected_total) > _TOLERANCE:
            all_ok = False
            issues.append(
                ValidationIssue(
                    rule_code="TAX_ARITHMETIC_MISMATCH",
                    severity=IssueSeverity.HIGH,
                    field=f"items[{idx}]",
                    message=(
                        f"Line {idx}: declared tax (₹{actual_total}) does not match the "
                        f"expected tax (₹{expected_total}) for a {item.gst_rate}% rate."
                    ),
                    recommendation="Verify the GST rate and tax split on this line item.",
                )
            )
    return all_ok


def _rule_invoice_totals_consistent(
    inv: InvoiceValidationInput, issues: list[ValidationIssue]
) -> bool:
    if inv.declared_taxable_value is None or not inv.items:
        return True

    computed_taxable = sum((i.taxable_value for i in inv.items), Decimal("0"))
    if abs(computed_taxable - inv.declared_taxable_value) > _TOLERANCE:
        issues.append(
            ValidationIssue(
                rule_code="TAXABLE_VALUE_MISMATCH",
                severity=IssueSeverity.HIGH,
                field="taxable_value",
                message=(
                    f"Sum of line-item taxable values (₹{computed_taxable}) does not match "
                    f"the declared invoice taxable value (₹{inv.declared_taxable_value})."
                ),
            )
        )
        return False
    return True


_ALL_RULES = [
    lambda inv, issues: _rule_gstin_present_and_valid(
        inv, "supplier_gstin", inv.supplier_gstin, issues
    ),
    lambda inv, issues: _rule_gstin_present_and_valid(inv, "buyer_gstin", inv.buyer_gstin, issues),
    _rule_invoice_number_present,
    _rule_no_duplicate_invoice_number,
    _rule_invoice_date_present,
    _rule_place_of_supply_present,
    _rule_line_items_present,
    _rule_hsn_sac_present,
    _rule_tax_arithmetic_matches_declared_rate,
    _rule_invoice_totals_consistent,
]


def validate_invoice(inv: InvoiceValidationInput) -> ValidationReport:
    issues: list[ValidationIssue] = []
    passed = 0

    for rule in _ALL_RULES:
        if rule(inv, issues):
            passed += 1

    total = len(_ALL_RULES)
    penalty = sum(_SEVERITY_PENALTY[i.severity] for i in issues)
    score = max(0, 100 - penalty)

    if any(i.severity == IssueSeverity.CRITICAL for i in issues):
        status = "FAILED"
    elif issues:
        status = "WARNING"
    else:
        status = "PASSED"

    return ValidationReport(
        status=status, score=score, passed_checks=passed, total_checks=total, issues=issues
    )
