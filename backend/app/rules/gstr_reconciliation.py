"""Deterministic GSTR-2A/2B reconciliation.

Matches an organization's purchase invoices (the "books") against
supplier-reported inward-supply records from a GSTR-2A/2B export (the
"return") for a tax period, and classifies every invoice/record into one of
four buckets: matched, mismatch, missing-in-return (claimed in books but the
supplier hasn't reported it — ITC at risk), or missing-in-books (reported by
the supplier but not recorded as a purchase invoice — a possible unclaimed
credit). Like every other module under `app/rules/`, this is a pure function
of the data handed to it — no DB, no LLM, no network — so it is fully
unit-testable and reproducible.

This does **not** call the GSTN API. `ReturnRecordInput` rows come from a
CSV a user downloads from the GST portal and uploads (see
app/services/reconciliation_service.py) — live GSTN integration is out of
scope, the same boundary already drawn for `app/rules/gstin_validator.py`
(structural checksum only, not live registration status).

Matching key: (supplier GSTIN, normalized invoice number). GSTN's own
matching tolerates incidental formatting differences in invoice numbers, so
the number is uppercased and stripped to alphanumerics before comparison;
the GSTIN is uppercased and stripped. A blank invoice number never matches
anything (it would otherwise collide every blank-numbered row together).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.models.reconciliation import ReconciliationMatchStatus

_ZERO = Decimal("0.00")
_DEFAULT_TAXABLE_VALUE_TOLERANCE = Decimal("1.00")
_DEFAULT_TAX_TOLERANCE = Decimal("1.00")

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def _normalize_gstin(gstin: str | None) -> str:
    return (gstin or "").strip().upper()


def _normalize_invoice_number(number: str | None) -> str:
    return _NON_ALNUM.sub("", (number or "").strip().upper())


def _match_key(gstin: str | None, invoice_number: str | None) -> tuple[str, str]:
    return _normalize_gstin(gstin), _normalize_invoice_number(invoice_number)


@dataclass
class BookInvoiceInput:
    invoice_id: str
    supplier_gstin: str | None
    invoice_number: str | None
    invoice_date: str | None
    taxable_value: Decimal
    total_tax: Decimal


@dataclass
class ReturnRecordInput:
    record_id: str
    supplier_gstin: str | None
    supplier_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    taxable_value: Decimal
    total_tax: Decimal


@dataclass
class ReconciliationResult:
    status: ReconciliationMatchStatus
    supplier_gstin: str | None
    invoice_number: str | None
    invoice_date: str | None
    book_invoice_id: str | None
    return_record_id: str | None
    book_taxable_value: Decimal | None
    book_tax: Decimal | None
    return_taxable_value: Decimal | None
    return_tax: Decimal | None
    taxable_value_difference: Decimal
    tax_difference: Decimal
    itc_at_risk: Decimal
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        def _s(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        return {
            "status": self.status.value,
            "supplier_gstin": self.supplier_gstin,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "book_invoice_id": self.book_invoice_id,
            "return_record_id": self.return_record_id,
            "book_taxable_value": _s(self.book_taxable_value),
            "book_tax": _s(self.book_tax),
            "return_taxable_value": _s(self.return_taxable_value),
            "return_tax": _s(self.return_tax),
            "taxable_value_difference": str(self.taxable_value_difference),
            "tax_difference": str(self.tax_difference),
            "itc_at_risk": str(self.itc_at_risk),
            "reasons": self.reasons,
        }


def _missing_in_return(inv: BookInvoiceInput, reason: str) -> ReconciliationResult:
    return ReconciliationResult(
        status=ReconciliationMatchStatus.MISSING_IN_RETURN,
        supplier_gstin=inv.supplier_gstin,
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        book_invoice_id=inv.invoice_id,
        return_record_id=None,
        book_taxable_value=inv.taxable_value,
        book_tax=inv.total_tax,
        return_taxable_value=None,
        return_tax=None,
        taxable_value_difference=inv.taxable_value,
        tax_difference=inv.total_tax,
        itc_at_risk=inv.total_tax,
        reasons=[reason],
    )


def _missing_in_books(rec: ReturnRecordInput, reason: str) -> ReconciliationResult:
    return ReconciliationResult(
        status=ReconciliationMatchStatus.MISSING_IN_BOOKS,
        supplier_gstin=rec.supplier_gstin,
        invoice_number=rec.invoice_number,
        invoice_date=rec.invoice_date,
        book_invoice_id=None,
        return_record_id=rec.record_id,
        book_taxable_value=None,
        book_tax=None,
        return_taxable_value=rec.taxable_value,
        return_tax=rec.total_tax,
        taxable_value_difference=rec.taxable_value,
        tax_difference=rec.total_tax,
        itc_at_risk=_ZERO,
        reasons=[reason],
    )


def reconcile(
    book_invoices: list[BookInvoiceInput],
    return_records: list[ReturnRecordInput],
    *,
    taxable_value_tolerance: Decimal = _DEFAULT_TAXABLE_VALUE_TOLERANCE,
    tax_tolerance: Decimal = _DEFAULT_TAX_TOLERANCE,
) -> list[ReconciliationResult]:
    """Reconcile purchase-side books against a supplier-reported 2A/2B
    extract for one period. Invoice numbers with the same normalized key
    are paired positionally (handles the rare case of a supplier re-using
    an invoice number); any count mismatch within a key falls through as
    missing/extra rows rather than being silently dropped."""
    # A blank invoice number can never be matched (otherwise every
    # blank-numbered row would collide with every other one), but it must
    # still be *reported* — so these are routed straight to their
    # unmatched bucket rather than going through the keyed lookup at all.
    books_by_key: dict[tuple[str, str], list[BookInvoiceInput]] = {}
    unmatchable_books: list[BookInvoiceInput] = []
    for inv in book_invoices:
        key = _match_key(inv.supplier_gstin, inv.invoice_number)
        if key[1]:
            books_by_key.setdefault(key, []).append(inv)
        else:
            unmatchable_books.append(inv)

    records_by_key: dict[tuple[str, str], list[ReturnRecordInput]] = {}
    unmatchable_records: list[ReturnRecordInput] = []
    for rec in return_records:
        key = _match_key(rec.supplier_gstin, rec.invoice_number)
        if key[1]:
            records_by_key.setdefault(key, []).append(rec)
        else:
            unmatchable_records.append(rec)

    results: list[ReconciliationResult] = []
    matched_keys: set[tuple[str, str]] = set()

    for inv in unmatchable_books:
        results.append(
            _missing_in_return(
                inv,
                "This invoice has no invoice number, so it cannot be matched against the "
                "supplier's GSTR-2A/2B — add the invoice number to reconcile it.",
            )
        )
    for rec in unmatchable_records:
        results.append(
            _missing_in_books(
                rec,
                "This GSTR-2A/2B row has no invoice number, so it cannot be matched against "
                "your books.",
            )
        )

    for key, invs in books_by_key.items():
        recs = records_by_key.get(key)

        if not recs:
            for inv in invs:
                results.append(
                    _missing_in_return(
                        inv,
                        "This invoice is in your books but was not found in the supplier's "
                        "GSTR-2A/2B for this period — the supplier may not have filed it "
                        "yet, or filed it under a different GSTIN/invoice number.",
                    )
                )
            continue

        matched_keys.add(key)
        for inv, rec in zip(invs, recs, strict=False):
            taxable_diff = (inv.taxable_value - rec.taxable_value).copy_abs()
            tax_diff = (inv.total_tax - rec.total_tax).copy_abs()

            if taxable_diff <= taxable_value_tolerance and tax_diff <= tax_tolerance:
                results.append(
                    ReconciliationResult(
                        status=ReconciliationMatchStatus.MATCHED,
                        supplier_gstin=inv.supplier_gstin,
                        invoice_number=inv.invoice_number,
                        invoice_date=inv.invoice_date,
                        book_invoice_id=inv.invoice_id,
                        return_record_id=rec.record_id,
                        book_taxable_value=inv.taxable_value,
                        book_tax=inv.total_tax,
                        return_taxable_value=rec.taxable_value,
                        return_tax=rec.total_tax,
                        taxable_value_difference=taxable_diff,
                        tax_difference=tax_diff,
                        itc_at_risk=_ZERO,
                        reasons=[],
                    )
                )
                continue

            reasons = []
            if taxable_diff > taxable_value_tolerance:
                reasons.append(
                    f"Taxable value differs: books ₹{inv.taxable_value} vs "
                    f"2A/2B ₹{rec.taxable_value}."
                )
            if tax_diff > tax_tolerance:
                reasons.append(
                    f"Tax amount differs: books ₹{inv.total_tax} vs "
                    f"2A/2B ₹{rec.total_tax}."
                )
            # Only the excess you've claimed over what the supplier actually
            # reported is at risk — under-claiming relative to 2A/2B is not
            # a compliance risk, just a missed opportunity.
            itc_at_risk = max(inv.total_tax - rec.total_tax, _ZERO)
            results.append(
                ReconciliationResult(
                    status=ReconciliationMatchStatus.MISMATCH,
                    supplier_gstin=inv.supplier_gstin,
                    invoice_number=inv.invoice_number,
                    invoice_date=inv.invoice_date,
                    book_invoice_id=inv.invoice_id,
                    return_record_id=rec.record_id,
                    book_taxable_value=inv.taxable_value,
                    book_tax=inv.total_tax,
                    return_taxable_value=rec.taxable_value,
                    return_tax=rec.total_tax,
                    taxable_value_difference=taxable_diff,
                    tax_difference=tax_diff,
                    itc_at_risk=itc_at_risk,
                    reasons=reasons,
                )
            )

        for extra_inv in invs[len(recs) :]:
            results.append(
                _missing_in_return(
                    extra_inv,
                    "Duplicate invoice number for this supplier without a matching "
                    "2A/2B entry.",
                )
            )
        for extra_rec in recs[len(invs) :]:
            results.append(
                _missing_in_books(
                    extra_rec,
                    "Duplicate invoice number in the supplier's 2A/2B without a matching "
                    "purchase invoice recorded in your books.",
                )
            )

    for key, recs in records_by_key.items():
        if key in matched_keys:
            continue
        for rec in recs:
            results.append(
                _missing_in_books(
                    rec,
                    "This supplier invoice appears in GSTR-2A/2B but no matching purchase "
                    "invoice is recorded in your books — you may be missing an eligible "
                    "ITC claim, or this belongs to a different entity.",
                )
            )

    return results


@dataclass
class ReconciliationSummary:
    total_book_invoices: int
    total_return_records: int
    matched: int
    mismatch: int
    missing_in_return: int
    missing_in_books: int
    itc_at_risk: Decimal
    potential_unclaimed_itc: Decimal

    def as_dict(self) -> dict:
        return {
            "total_book_invoices": self.total_book_invoices,
            "total_return_records": self.total_return_records,
            "matched": self.matched,
            "mismatch": self.mismatch,
            "missing_in_return": self.missing_in_return,
            "missing_in_books": self.missing_in_books,
            "itc_at_risk": str(self.itc_at_risk),
            "potential_unclaimed_itc": str(self.potential_unclaimed_itc),
        }


def summarize(results: list[ReconciliationResult]) -> ReconciliationSummary:
    counts = dict.fromkeys(ReconciliationMatchStatus, 0)
    itc_at_risk = _ZERO
    potential_unclaimed = _ZERO
    book_count = 0
    return_count = 0

    for r in results:
        counts[r.status] += 1
        itc_at_risk += r.itc_at_risk
        if r.status == ReconciliationMatchStatus.MISSING_IN_BOOKS:
            potential_unclaimed += r.return_tax or _ZERO
        if r.book_invoice_id is not None:
            book_count += 1
        if r.return_record_id is not None:
            return_count += 1

    return ReconciliationSummary(
        total_book_invoices=book_count,
        total_return_records=return_count,
        matched=counts[ReconciliationMatchStatus.MATCHED],
        mismatch=counts[ReconciliationMatchStatus.MISMATCH],
        missing_in_return=counts[ReconciliationMatchStatus.MISSING_IN_RETURN],
        missing_in_books=counts[ReconciliationMatchStatus.MISSING_IN_BOOKS],
        itc_at_risk=itc_at_risk,
        potential_unclaimed_itc=potential_unclaimed,
    )
