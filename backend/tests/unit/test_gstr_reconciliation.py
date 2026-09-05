"""Unit tests for the deterministic GSTR-2A/2B reconciliation (LLM/DB-free)."""

from __future__ import annotations

from decimal import Decimal

from app.models.reconciliation import ReconciliationMatchStatus
from app.rules.gstr_reconciliation import (
    BookInvoiceInput,
    ReturnRecordInput,
    reconcile,
    summarize,
)

D = Decimal
GSTIN = "27AAAAA0000A1Z5"


def _book(invoice_id="inv-1", gstin=GSTIN, number="INV-001", date="2026-01-10",
          taxable=1000, tax=180):
    return BookInvoiceInput(
        invoice_id=invoice_id,
        supplier_gstin=gstin,
        invoice_number=number,
        invoice_date=date,
        taxable_value=D(str(taxable)),
        total_tax=D(str(tax)),
    )


def _record(record_id="rec-1", gstin=GSTIN, number="INV-001", date="2026-01-10",
            taxable=1000, tax=180, name="Vendor Pvt Ltd"):
    return ReturnRecordInput(
        record_id=record_id,
        supplier_gstin=gstin,
        supplier_name=name,
        invoice_number=number,
        invoice_date=date,
        taxable_value=D(str(taxable)),
        total_tax=D(str(tax)),
    )


def test_matched_within_tolerance():
    results = reconcile([_book()], [_record()])
    assert len(results) == 1
    assert results[0].status == ReconciliationMatchStatus.MATCHED
    assert results[0].itc_at_risk == D("0")
    assert results[0].reasons == []


def test_invoice_number_normalization_ignores_case_and_punctuation():
    book = _book(number="inv/001-A")
    record = _record(number="INV001A")
    results = reconcile([book], [record])
    assert len(results) == 1
    assert results[0].status == ReconciliationMatchStatus.MATCHED


def test_small_difference_within_tolerance_still_matches():
    book = _book(taxable=1000, tax=180)
    record = _record(taxable="1000.50", tax="180.20")
    results = reconcile([book], [record])
    assert results[0].status == ReconciliationMatchStatus.MATCHED


def test_mismatch_beyond_tolerance_reports_itc_at_risk_as_excess_claimed():
    book = _book(taxable=1000, tax=200)  # claimed 200
    record = _record(taxable=1000, tax=180)  # supplier only reported 180
    results = reconcile([book], [record])
    assert len(results) == 1
    result = results[0]
    assert result.status == ReconciliationMatchStatus.MISMATCH
    assert result.tax_difference == D("20")
    assert result.itc_at_risk == D("20")  # only the excess over what supplier reported
    assert any("Tax amount differs" in r for r in result.reasons)


def test_mismatch_where_books_understate_has_zero_itc_at_risk():
    book = _book(taxable=1000, tax=150)  # claimed less than reported
    record = _record(taxable=1000, tax=180)
    results = reconcile([book], [record])
    result = results[0]
    assert result.status == ReconciliationMatchStatus.MISMATCH
    assert result.itc_at_risk == D("0")  # under-claiming is a missed opportunity, not a risk


def test_missing_in_return_when_book_invoice_has_no_return_record():
    results = reconcile([_book()], [])
    assert len(results) == 1
    result = results[0]
    assert result.status == ReconciliationMatchStatus.MISSING_IN_RETURN
    assert result.itc_at_risk == D("180")
    assert result.return_record_id is None


def test_missing_in_books_when_return_record_has_no_book_invoice():
    results = reconcile([], [_record()])
    assert len(results) == 1
    result = results[0]
    assert result.status == ReconciliationMatchStatus.MISSING_IN_BOOKS
    assert result.itc_at_risk == D("0")
    assert result.book_invoice_id is None


def test_blank_invoice_numbers_never_collide():
    book = _book(number="")
    record = _record(number="")
    results = reconcile([book], [record])
    statuses = {r.status for r in results}
    assert statuses == {
        ReconciliationMatchStatus.MISSING_IN_RETURN,
        ReconciliationMatchStatus.MISSING_IN_BOOKS,
    }


def test_summarize_totals_across_all_buckets():
    books = [
        _book(invoice_id="i1", number="A1", taxable=1000, tax=180),  # matched
        _book(invoice_id="i2", number="A2", taxable=1000, tax=200),  # mismatch, 20 at risk
        _book(invoice_id="i3", number="A3", taxable=500, tax=90),  # missing in return
    ]
    records = [
        _record(record_id="r1", number="A1", taxable=1000, tax=180),
        _record(record_id="r2", number="A2", taxable=1000, tax=180),
        _record(record_id="r4", number="A4", taxable=2000, tax=360),  # missing in books
    ]
    results = reconcile(books, records)
    summary = summarize(results)

    assert summary.total_book_invoices == 3
    assert summary.total_return_records == 3
    assert summary.matched == 1
    assert summary.mismatch == 1
    assert summary.missing_in_return == 1
    assert summary.missing_in_books == 1
    assert summary.itc_at_risk == D("20") + D("90")  # mismatch excess + fully unreported
    assert summary.potential_unclaimed_itc == D("360")
