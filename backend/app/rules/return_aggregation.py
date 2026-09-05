"""Deterministic GST return aggregation.

Turns a set of invoices for a tax period into the summary figures that go
onto GSTR-1 (outward supplies) and GSTR-3B (monthly summary). Like every
other module under `app/rules/`, this has zero dependency on the LLM, the
database or the network — it is a pure function of the invoice data handed
to it, so the whole thing is unit-testable in isolation and reproducible.

This is emphatically **not** a filing integration: it produces the numbers
a human reviewer checks and exports, nothing is transmitted to the GSTN.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

_ZERO = Decimal("0.00")


@dataclass
class ReturnLineInput:
    taxable_value: Decimal
    gst_rate: Decimal
    cgst: Decimal = _ZERO
    sgst: Decimal = _ZERO
    igst: Decimal = _ZERO
    cess: Decimal = _ZERO


@dataclass
class ReturnInvoiceInput:
    direction: str  # "sales" | "purchase"
    invoice_number: str | None
    invoice_date: str | None  # ISO YYYY-MM-DD
    counterparty_name: str | None
    counterparty_gstin: str | None
    place_of_supply: str | None
    lines: list[ReturnLineInput] = field(default_factory=list)


@dataclass
class TaxTotals:
    taxable_value: Decimal = _ZERO
    cgst: Decimal = _ZERO
    sgst: Decimal = _ZERO
    igst: Decimal = _ZERO
    cess: Decimal = _ZERO

    @property
    def total_tax(self) -> Decimal:
        return self.cgst + self.sgst + self.igst + self.cess

    def add_line(self, line: ReturnLineInput) -> None:
        self.taxable_value += line.taxable_value
        self.cgst += line.cgst
        self.sgst += line.sgst
        self.igst += line.igst
        self.cess += line.cess

    def as_dict(self) -> dict[str, str]:
        return {
            "taxable_value": str(self.taxable_value),
            "cgst": str(self.cgst),
            "sgst": str(self.sgst),
            "igst": str(self.igst),
            "cess": str(self.cess),
            "total_tax": str(self.total_tax),
        }


@dataclass
class RateBucket:
    gst_rate: Decimal
    totals: TaxTotals = field(default_factory=TaxTotals)

    def as_dict(self) -> dict:
        return {"gst_rate": str(self.gst_rate), **self.totals.as_dict()}


@dataclass
class CounterpartyGroup:
    gstin: str | None
    name: str | None
    invoice_count: int
    totals: TaxTotals
    rate_buckets: list[RateBucket]

    def as_dict(self) -> dict:
        return {
            "gstin": self.gstin,
            "name": self.name,
            "invoice_count": self.invoice_count,
            **self.totals.as_dict(),
            "rate_breakdown": [b.as_dict() for b in self.rate_buckets],
        }


def _bucket_by_rate(lines: list[ReturnLineInput]) -> list[RateBucket]:
    by_rate: dict[Decimal, RateBucket] = {}
    for line in lines:
        bucket = by_rate.setdefault(line.gst_rate, RateBucket(gst_rate=line.gst_rate))
        bucket.totals.add_line(line)
    return [by_rate[r] for r in sorted(by_rate)]


def _group_counterparties(invoices: list[ReturnInvoiceInput], *, with_gstin: bool) -> list[dict]:
    grouped: dict[str, list[ReturnInvoiceInput]] = defaultdict(list)
    for inv in invoices:
        has_gstin = bool(inv.counterparty_gstin)
        if has_gstin != with_gstin:
            continue
        key = inv.counterparty_gstin or (inv.place_of_supply or "unregistered")
        grouped[key].append(inv)

    groups: list[CounterpartyGroup] = []
    for key, invs in grouped.items():
        all_lines = [line for inv in invs for line in inv.lines]
        totals = TaxTotals()
        for line in all_lines:
            totals.add_line(line)
        groups.append(
            CounterpartyGroup(
                gstin=invs[0].counterparty_gstin,
                name=invs[0].counterparty_name or key,
                invoice_count=len(invs),
                totals=totals,
                rate_buckets=_bucket_by_rate(all_lines),
            )
        )
    groups.sort(key=lambda g: g.totals.taxable_value, reverse=True)
    return [g.as_dict() for g in groups]


@dataclass
class GSTR1Summary:
    period: str
    b2b: list[dict]
    b2c: list[dict]
    rate_wise: list[dict]
    totals: dict

    def as_dict(self) -> dict:
        return {
            "return_type": "gstr1",
            "period": self.period,
            "b2b": self.b2b,
            "b2c": self.b2c,
            "rate_wise": self.rate_wise,
            "totals": self.totals,
        }


@dataclass
class GSTR3BSummary:
    period: str
    outward_taxable: dict
    inward_itc: dict
    net_tax_payable: dict

    def as_dict(self) -> dict:
        return {
            "return_type": "gstr3b",
            "period": self.period,
            "outward_taxable_supplies": self.outward_taxable,
            "eligible_itc": self.inward_itc,
            "net_tax_payable": self.net_tax_payable,
        }


def _totals_for(invoices: list[ReturnInvoiceInput]) -> TaxTotals:
    totals = TaxTotals()
    for inv in invoices:
        for line in inv.lines:
            totals.add_line(line)
    return totals


def build_gstr1(period: str, invoices: list[ReturnInvoiceInput]) -> GSTR1Summary:
    sales = [inv for inv in invoices if inv.direction == "sales"]
    all_lines = [line for inv in sales for line in inv.lines]
    return GSTR1Summary(
        period=period,
        b2b=_group_counterparties(sales, with_gstin=True),
        b2c=_group_counterparties(sales, with_gstin=False),
        rate_wise=[b.as_dict() for b in _bucket_by_rate(all_lines)],
        totals=_totals_for(sales).as_dict(),
    )


def build_gstr3b(period: str, invoices: list[ReturnInvoiceInput]) -> GSTR3BSummary:
    sales = [inv for inv in invoices if inv.direction == "sales"]
    purchases = [inv for inv in invoices if inv.direction == "purchase"]

    outward = _totals_for(sales)
    itc = _totals_for(purchases)

    net_cgst = max(outward.cgst - itc.cgst, _ZERO)
    net_sgst = max(outward.sgst - itc.sgst, _ZERO)
    net_igst = max(outward.igst - itc.igst, _ZERO)
    net_cess = max(outward.cess - itc.cess, _ZERO)

    return GSTR3BSummary(
        period=period,
        outward_taxable=outward.as_dict(),
        inward_itc=itc.as_dict(),
        net_tax_payable={
            "cgst": str(net_cgst),
            "sgst": str(net_sgst),
            "igst": str(net_igst),
            "cess": str(net_cess),
            "total_tax": str(net_cgst + net_sgst + net_igst + net_cess),
        },
    )


def gstr1_to_csv_rows(summary: GSTR1Summary) -> list[list[str]]:
    """Flatten a GSTR-1 summary into rate-wise CSV rows a reviewer can open
    in a spreadsheet. Header first."""
    rows = [
        [
            "section",
            "counterparty_gstin",
            "counterparty_name",
            "gst_rate",
            "taxable_value",
            "igst",
            "cgst",
            "sgst",
            "cess",
        ]
    ]
    for section, groups in (("B2B", summary.b2b), ("B2C", summary.b2c)):
        for group in groups:
            for bucket in group["rate_breakdown"]:
                rows.append(
                    [
                        section,
                        group.get("gstin") or "",
                        group.get("name") or "",
                        bucket["gst_rate"],
                        bucket["taxable_value"],
                        bucket["igst"],
                        bucket["cgst"],
                        bucket["sgst"],
                        bucket["cess"],
                    ]
                )
    return rows
