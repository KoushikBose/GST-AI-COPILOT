"""Unit tests for the deterministic GST return aggregation (LLM/DB-free)."""

from __future__ import annotations

from decimal import Decimal

from app.rules.return_aggregation import (
    ReturnInvoiceInput,
    ReturnLineInput,
    build_gstr1,
    build_gstr3b,
    gstr1_to_csv_rows,
)

D = Decimal


def _line(taxable, rate, *, cgst=0, sgst=0, igst=0, cess=0):
    return ReturnLineInput(
        taxable_value=D(str(taxable)),
        gst_rate=D(str(rate)),
        cgst=D(str(cgst)),
        sgst=D(str(sgst)),
        igst=D(str(igst)),
        cess=D(str(cess)),
    )


def _sales(gstin, name, lines):
    return ReturnInvoiceInput(
        direction="sales",
        invoice_number="S1",
        invoice_date="2026-01-10",
        counterparty_name=name,
        counterparty_gstin=gstin,
        place_of_supply="Maharashtra",
        lines=lines,
    )


def _purchase(lines):
    return ReturnInvoiceInput(
        direction="purchase",
        invoice_number="P1",
        invoice_date="2026-01-12",
        counterparty_name="Vendor",
        counterparty_gstin="27AAAAA0000A1Z5",
        place_of_supply="Maharashtra",
        lines=lines,
    )


def test_gstr1_splits_b2b_and_b2c():
    invoices = [
        _sales("27BBBBB1111B1Z5", "Registered Buyer", [_line(1000, 18, cgst=90, sgst=90)]),
        _sales(None, "Walk-in", [_line(500, 5, cgst="12.50", sgst="12.50")]),
    ]
    summary = build_gstr1("2026-01", invoices)

    assert len(summary.b2b) == 1
    assert len(summary.b2c) == 1
    assert summary.b2b[0]["gstin"] == "27BBBBB1111B1Z5"
    assert D(summary.totals["taxable_value"]) == D("1500")
    assert D(summary.totals["total_tax"]) == D("205")


def test_gstr1_rate_wise_buckets_aggregate_across_invoices():
    invoices = [
        _sales("27CCCCC2222C1Z5", "A", [_line(1000, 18, igst=180)]),
        _sales("27DDDDD3333D1Z5", "B", [_line(2000, 18, igst=360)]),
        _sales("27EEEEE4444E1Z5", "C", [_line(400, 5, igst=20)]),
    ]
    summary = build_gstr1("2026-01", invoices)
    by_rate = {b["gst_rate"]: b for b in summary.rate_wise}
    assert D(by_rate["18"]["taxable_value"]) == D("3000")
    assert D(by_rate["18"]["igst"]) == D("540")
    assert D(by_rate["5"]["taxable_value"]) == D("400")


def test_gstr3b_nets_itc_against_output_tax_and_floors_at_zero():
    invoices = [
        _sales("27FFFFF5555F1Z5", "Buyer", [_line(10000, 18, igst=1800)]),
        _purchase([_line(4000, 18, igst=720)]),
        _purchase([_line(30000, 18, igst=5400)]),
    ]
    summary = build_gstr3b("2026-01", invoices)
    assert D(summary.outward_taxable["igst"]) == D("1800")
    assert D(summary.inward_itc["igst"]) == D("6120")
    assert D(summary.net_tax_payable["igst"]) == D("0")
    assert D(summary.net_tax_payable["total_tax"]) == D("0")


def test_gstr1_csv_has_header_and_one_row_per_rate_bucket():
    invoices = [
        _sales(
            "27GGGGG6666G1Z5",
            "Buyer",
            [_line(1000, 18, igst=180), _line(500, 5, igst=25)],
        )
    ]
    rows = gstr1_to_csv_rows(build_gstr1("2026-01", invoices))
    assert rows[0][0] == "section"
    assert len(rows) == 3  # header + 2 rate buckets
    assert {r[3] for r in rows[1:]} == {"18", "5"}
