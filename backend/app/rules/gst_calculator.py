"""Deterministic GST calculation engine.

This module is the single source of truth for GST arithmetic. It has no
dependency on the LLM, agents, or the database, and must remain fully
unit-testable in isolation (see tests/unit/test_gst_calculator.py).

Rules are versioned via `rules_version` so a change in rounding/behavior can
be introduced without silently altering historical calculations that were
already persisted and shown to a user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from app.core.errors import ValidationFailedError

TWO_PLACES = Decimal("0.01")


class TransactionType(StrEnum):
    INTRA_STATE = "intra_state"  # CGST + SGST
    INTER_STATE = "inter_state"  # IGST
    EXPORT = "export"  # zero-rated (typically 0%, subject to LUT/bond rules)
    SEZ_SUPPLY = "sez_supply"  # zero-rated to SEZ
    EXEMPT = "exempt"  # no GST applies
    NIL_RATED = "nil_rated"  # 0% GST, still a taxable supply category


ZERO_TAX_TRANSACTION_TYPES = frozenset(
    {
        TransactionType.EXPORT,
        TransactionType.SEZ_SUPPLY,
        TransactionType.EXEMPT,
        TransactionType.NIL_RATED,
    }
)


@dataclass(frozen=True)
class GSTCalculation:
    rules_version: str
    transaction_type: TransactionType
    taxable_value: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    cess: Decimal
    total_tax: Decimal
    grand_total: Decimal
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, str]:
        return {
            "rules_version": self.rules_version,
            "transaction_type": self.transaction_type.value,
            "taxable_value": str(self.taxable_value),
            "gst_rate": str(self.gst_rate),
            "cess_rate": str(self.cess_rate),
            "cgst": str(self.cgst),
            "sgst": str(self.sgst),
            "igst": str(self.igst),
            "cess": str(self.cess),
            "total_tax": str(self.total_tax),
            "grand_total": str(self.grand_total),
            "warnings": self.warnings,
        }


def _to_decimal(value: Decimal | str | int | float, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationFailedError(f"Invalid numeric value for '{field_name}': {value!r}") from exc


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class GSTCalculator:
    """Deterministic GST calculator.

    `rules_version` pins the calculation behavior (currently only affects
    the rounding strategy, but future changes to e.g. cess handling or
    composition-scheme logic should branch on it rather than mutating
    behavior for a fixed version in place).
    """

    def __init__(self, rules_version: str = "2026.01") -> None:
        self.rules_version = rules_version

    def calculate(
        self,
        *,
        taxable_value: Decimal | str | int | float,
        gst_rate: Decimal | str | int | float,
        transaction_type: TransactionType | str,
        cess_rate: Decimal | str | int | float = 0,
    ) -> GSTCalculation:
        taxable = _to_decimal(taxable_value, "taxable_value")
        rate = _to_decimal(gst_rate, "gst_rate")
        cess_rate_dec = _to_decimal(cess_rate, "cess_rate")
        txn_type = TransactionType(transaction_type)

        warnings: list[str] = []

        if taxable < 0:
            raise ValidationFailedError("taxable_value cannot be negative.")
        if rate < 0 or rate > 100:
            raise ValidationFailedError("gst_rate must be between 0 and 100.")
        if cess_rate_dec < 0:
            raise ValidationFailedError("cess_rate cannot be negative.")

        if txn_type in ZERO_TAX_TRANSACTION_TYPES:
            if rate != 0:
                warnings.append(
                    f"gst_rate {rate} was provided for a {txn_type.value} transaction; "
                    "treating tax as zero. Verify LUT/bond or exemption applicability."
                )
            cgst = sgst = igst = cess = Decimal("0.00")
        elif txn_type == TransactionType.INTRA_STATE:
            half_rate = rate / 2
            cgst = _round(taxable * half_rate / 100)
            sgst = _round(taxable * half_rate / 100)
            igst = Decimal("0.00")
            cess = _round(taxable * cess_rate_dec / 100)
        elif txn_type == TransactionType.INTER_STATE:
            cgst = sgst = Decimal("0.00")
            igst = _round(taxable * rate / 100)
            cess = _round(taxable * cess_rate_dec / 100)
        else:  # pragma: no cover - exhaustive StrEnum guard
            raise ValidationFailedError(f"Unsupported transaction_type: {txn_type}")

        total_tax = cgst + sgst + igst + cess
        grand_total = _round(taxable) + total_tax

        return GSTCalculation(
            rules_version=self.rules_version,
            transaction_type=txn_type,
            taxable_value=_round(taxable),
            gst_rate=rate,
            cess_rate=cess_rate_dec,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            cess=cess,
            total_tax=total_tax,
            grand_total=grand_total,
            warnings=warnings,
        )

    def calculate_line_items(
        self,
        items: list[dict],
        *,
        transaction_type: TransactionType | str,
    ) -> tuple[list[GSTCalculation], GSTCalculation]:
        """Calculate GST per line item and return (line_results, invoice_total).

        Each item dict must contain `taxable_value` and `gst_rate`, and may
        contain `cess_rate`. Invoice-level totals are the sum of line-level
        (already-rounded) components — this matches standard GST invoicing
        practice of rounding at the line level, not just at the total.
        """
        if not items:
            raise ValidationFailedError("At least one line item is required.")

        results = [
            self.calculate(
                taxable_value=item["taxable_value"],
                gst_rate=item["gst_rate"],
                transaction_type=transaction_type,
                cess_rate=item.get("cess_rate", 0),
            )
            for item in items
        ]

        txn_type = TransactionType(transaction_type)
        total = GSTCalculation(
            rules_version=self.rules_version,
            transaction_type=txn_type,
            taxable_value=sum((r.taxable_value for r in results), Decimal("0.00")),
            gst_rate=Decimal("0"),  # not meaningful at aggregate level (rates may differ)
            cess_rate=Decimal("0"),
            cgst=sum((r.cgst for r in results), Decimal("0.00")),
            sgst=sum((r.sgst for r in results), Decimal("0.00")),
            igst=sum((r.igst for r in results), Decimal("0.00")),
            cess=sum((r.cess for r in results), Decimal("0.00")),
            total_tax=sum((r.total_tax for r in results), Decimal("0.00")),
            grand_total=sum((r.grand_total for r in results), Decimal("0.00")),
            warnings=[w for r in results for w in r.warnings],
        )
        return results, total
