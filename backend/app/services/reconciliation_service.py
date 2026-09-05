"""GSTR-2A/2B reconciliation service.

Imports a supplier-reported GSTR-2A/2B CSV export, then reconciles it
against the organization's purchase invoices for the same period. All
matching arithmetic is delegated to the deterministic
`app.rules.gstr_reconciliation` module; this service only does CSV parsing,
ORM <-> plain-input adaptation, persistence, and CSV export of the results.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.reconciliation import (
    Gstr2bRecord,
    ReconciliationMatch,
    ReconciliationMatchStatus,
    ReconciliationRun,
    ReconciliationSource,
)
from app.rules.gstr_reconciliation import (
    BookInvoiceInput,
    ReturnRecordInput,
    reconcile,
    summarize,
)

logger = get_logger(__name__)

_PERIOD_LEN = 7  # "YYYY-MM"
_EXCLUDED_INVOICE_STATUSES = {InvoiceStatus.FAILED, InvoiceStatus.REJECTED}

# GSTN 2A/2B portal exports vary in header casing/wording across formats;
# accept a few common aliases per logical column rather than forcing one
# exact header row.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "supplier_gstin": ("supplier_gstin", "gstin of supplier", "gstin", "supplier gstin"),
    "supplier_name": ("supplier_name", "trade/legal name", "supplier name"),
    "invoice_number": ("invoice_number", "invoice number", "invoice no", "invoice no."),
    "invoice_date": ("invoice_date", "invoice date"),
    "taxable_value": ("taxable_value", "taxable value (₹)", "taxable value"),
    "igst": ("igst", "integrated tax(₹)", "integrated tax", "igst amount"),
    "cgst": ("cgst", "central tax(₹)", "central tax", "cgst amount"),
    "sgst": ("sgst", "state/ut tax(₹)", "state/ut tax", "state tax", "sgst amount"),
    "cess": ("cess", "cess(₹)", "cess amount"),
}
_REQUIRED_COLUMNS = {"supplier_gstin", "invoice_number", "taxable_value"}


def _validate_period(period: str) -> None:
    if len(period) != _PERIOD_LEN or period[4] != "-":
        raise ValidationFailedError("period must be in 'YYYY-MM' format.")
    year, month = period[:4], period[5:]
    if not (year.isdigit() and month.isdigit() and 1 <= int(month) <= 12):
        raise ValidationFailedError("period must be a valid calendar month, e.g. '2026-01'.")


def _decimal(raw: str | None) -> Decimal:
    if raw is None or not raw.strip():
        return Decimal("0")
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _build_column_map(header: list[str]) -> dict[str, str]:
    """Maps a logical field name -> the actual header cell that supplies it."""
    normalized = {cell.strip().lower(): cell for cell in header}
    mapping: dict[str, str] = {}
    for logical_field, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[logical_field] = normalized[alias]
                break
    return mapping


class ReconciliationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------------------------------------------------------- CSV --

    def parse_csv(self, content: bytes) -> list[dict[str, str]]:
        """Parses a GSTR-2A/2B CSV export into plain dicts keyed by logical
        field name. Raises ValidationFailedError on a malformed/incomplete
        file — this never touches the database."""
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationFailedError("File must be UTF-8 encoded CSV.") from exc

        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise ValidationFailedError("CSV file is empty.")

        header, *data_rows = rows
        column_map = _build_column_map(header)
        missing = _REQUIRED_COLUMNS - column_map.keys()
        if missing:
            raise ValidationFailedError(
                f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
                "Expected at least: supplier_gstin, invoice_number, taxable_value "
                "(supplier_name, invoice_date, igst, cgst, sgst, cess are optional)."
            )

        column_index = {cell: i for i, cell in enumerate(header)}
        parsed: list[dict[str, str]] = []
        for row in data_rows:
            if not any(cell.strip() for cell in row):
                continue  # skip blank rows
            record: dict[str, str] = {}
            for logical_field, header_cell in column_map.items():
                idx = column_index[header_cell]
                record[logical_field] = row[idx] if idx < len(row) else ""
            parsed.append(record)

        if not parsed:
            raise ValidationFailedError("CSV has a header row but no data rows.")
        return parsed

    # ------------------------------------------------------------- import --

    async def import_records(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        period: str,
        source: ReconciliationSource,
        rows: list[dict[str, str]],
    ) -> int:
        _validate_period(period)
        if not rows:
            raise ValidationFailedError("No data rows found in the uploaded file.")

        # Re-uploading a period+source replaces its records outright, so a
        # corrected export never leaves stale rows behind.
        await self.session.execute(
            delete(Gstr2bRecord).where(
                Gstr2bRecord.organization_id == organization_id,
                Gstr2bRecord.period == period,
                Gstr2bRecord.source == source,
            )
        )

        for i, row in enumerate(rows):
            self.session.add(
                Gstr2bRecord(
                    organization_id=organization_id,
                    period=period,
                    source=source,
                    row_number=i,
                    supplier_gstin=(row.get("supplier_gstin") or "").strip().upper() or None,
                    supplier_name=(row.get("supplier_name") or "").strip() or None,
                    invoice_number=(row.get("invoice_number") or "").strip() or None,
                    invoice_date=(row.get("invoice_date") or "").strip() or None,
                    taxable_value=_decimal(row.get("taxable_value")),
                    igst=_decimal(row.get("igst")),
                    cgst=_decimal(row.get("cgst")),
                    sgst=_decimal(row.get("sgst")),
                    cess=_decimal(row.get("cess")),
                    uploaded_by=user_id,
                )
            )

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="reconciliation.import",
                entity_type="gstr2b_record",
                entity_id=period,
                metadata_json={"source": source.value, "row_count": len(rows)},
            )
        )
        await self.session.flush()
        logger.info(
            "gstr2b_records_imported", period=period, source=source.value, row_count=len(rows)
        )
        return len(rows)

    # ---------------------------------------------------------------- run --

    async def _load_purchase_invoices(
        self, *, organization_id: uuid.UUID, period: str
    ) -> list[Invoice]:
        stmt = select(Invoice).where(
            Invoice.organization_id == organization_id,
            Invoice.direction == InvoiceDirection.PURCHASE,
            Invoice.invoice_date.is_not(None),
            Invoice.invoice_date.like(f"{period}-%"),
            Invoice.status.not_in(_EXCLUDED_INVOICE_STATUSES),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _load_records(
        self, *, organization_id: uuid.UUID, period: str, source: ReconciliationSource
    ) -> list[Gstr2bRecord]:
        stmt = select(Gstr2bRecord).where(
            Gstr2bRecord.organization_id == organization_id,
            Gstr2bRecord.period == period,
            Gstr2bRecord.source == source,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def run(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        period: str,
        source: ReconciliationSource = ReconciliationSource.GSTR2B,
    ) -> ReconciliationRun:
        _validate_period(period)

        invoices = await self._load_purchase_invoices(
            organization_id=organization_id, period=period
        )
        records = await self._load_records(
            organization_id=organization_id, period=period, source=source
        )
        if not records:
            raise ValidationFailedError(
                f"No {source.value.upper()} data uploaded for {period} yet — "
                "upload it first via POST /reconciliation/upload."
            )

        book_inputs = [
            BookInvoiceInput(
                invoice_id=str(inv.id),
                supplier_gstin=inv.supplier_gstin,
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date,
                taxable_value=inv.taxable_value or Decimal("0"),
                total_tax=inv.total_tax or Decimal("0"),
            )
            for inv in invoices
        ]
        return_inputs = [
            ReturnRecordInput(
                record_id=str(rec.id),
                supplier_gstin=rec.supplier_gstin,
                supplier_name=rec.supplier_name,
                invoice_number=rec.invoice_number,
                invoice_date=rec.invoice_date,
                taxable_value=rec.taxable_value,
                total_tax=rec.igst + rec.cgst + rec.sgst + rec.cess,
            )
            for rec in records
        ]

        results = reconcile(book_inputs, return_inputs)
        summary = summarize(results)

        existing = await self.session.execute(
            select(ReconciliationRun).where(
                ReconciliationRun.organization_id == organization_id,
                ReconciliationRun.period == period,
            )
        )
        run_row = existing.scalar_one_or_none()
        if run_row is None:
            run_row = ReconciliationRun(organization_id=organization_id, period=period)
            self.session.add(run_row)
        else:
            await self.session.execute(
                delete(ReconciliationMatch).where(ReconciliationMatch.run_id == run_row.id)
            )

        run_row.source = source
        run_row.book_invoice_count = summary.total_book_invoices
        run_row.return_record_count = summary.total_return_records
        run_row.matched_count = summary.matched
        run_row.mismatch_count = summary.mismatch
        run_row.missing_in_return_count = summary.missing_in_return
        run_row.missing_in_books_count = summary.missing_in_books
        run_row.itc_at_risk = summary.itc_at_risk
        run_row.potential_unclaimed_itc = summary.potential_unclaimed_itc
        run_row.run_by = user_id
        await self.session.flush()  # assigns run_row.id for a brand-new run

        for r in results:
            self.session.add(
                ReconciliationMatch(
                    organization_id=organization_id,
                    run_id=run_row.id,
                    status=r.status,
                    invoice_id=uuid.UUID(r.book_invoice_id) if r.book_invoice_id else None,
                    gstr2b_record_id=(
                        uuid.UUID(r.return_record_id) if r.return_record_id else None
                    ),
                    supplier_gstin=r.supplier_gstin,
                    invoice_number=r.invoice_number,
                    invoice_date=r.invoice_date,
                    book_taxable_value=r.book_taxable_value,
                    book_tax=r.book_tax,
                    return_taxable_value=r.return_taxable_value,
                    return_tax=r.return_tax,
                    taxable_value_difference=r.taxable_value_difference,
                    tax_difference=r.tax_difference,
                    itc_at_risk=r.itc_at_risk,
                    reasons=r.reasons,
                )
            )

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="reconciliation.run",
                entity_type="reconciliation_run",
                entity_id=str(run_row.id),
                metadata_json={"period": period, "source": source.value, **summary.as_dict()},
            )
        )
        await self.session.flush()
        logger.info("reconciliation_run_completed", period=period, **summary.as_dict())
        return run_row

    # --------------------------------------------------------------- reads --

    async def list_runs(self, *, organization_id: uuid.UUID) -> list[ReconciliationRun]:
        result = await self.session.execute(
            select(ReconciliationRun)
            .where(ReconciliationRun.organization_id == organization_id)
            .order_by(ReconciliationRun.period.desc())
        )
        return list(result.scalars().all())

    async def get_run(
        self, *, organization_id: uuid.UUID, run_id: uuid.UUID
    ) -> ReconciliationRun:
        result = await self.session.execute(
            select(ReconciliationRun).where(
                ReconciliationRun.id == run_id,
                ReconciliationRun.organization_id == organization_id,
            )
        )
        run_row = result.scalar_one_or_none()
        if run_row is None:
            raise NotFoundError("Reconciliation run not found.")
        return run_row

    async def list_matches(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        status: ReconciliationMatchStatus | None = None,
    ) -> list[ReconciliationMatch]:
        await self.get_run(organization_id=organization_id, run_id=run_id)  # 404 + tenant check
        stmt = select(ReconciliationMatch).where(
            ReconciliationMatch.run_id == run_id,
            ReconciliationMatch.organization_id == organization_id,
        )
        if status is not None:
            stmt = stmt.where(ReconciliationMatch.status == status)
        stmt = stmt.order_by(ReconciliationMatch.invoice_date, ReconciliationMatch.invoice_number)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # -------------------------------------------------------------- export --

    def build_csv(self, matches: list[ReconciliationMatch]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "status",
                "supplier_gstin",
                "invoice_number",
                "invoice_date",
                "book_taxable_value",
                "book_tax",
                "return_taxable_value",
                "return_tax",
                "taxable_value_difference",
                "tax_difference",
                "itc_at_risk",
                "reasons",
            ]
        )
        for m in matches:
            writer.writerow(
                [
                    m.status.value,
                    m.supplier_gstin or "",
                    m.invoice_number or "",
                    m.invoice_date or "",
                    m.book_taxable_value if m.book_taxable_value is not None else "",
                    m.book_tax if m.book_tax is not None else "",
                    m.return_taxable_value if m.return_taxable_value is not None else "",
                    m.return_tax if m.return_tax is not None else "",
                    m.taxable_value_difference,
                    m.tax_difference,
                    m.itc_at_risk,
                    "; ".join(m.reasons or []),
                ]
            )
        return buffer.getvalue()

    async def export(
        self, *, organization_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[ReconciliationRun, str, str]:
        run_row = await self.get_run(organization_id=organization_id, run_id=run_id)
        matches = await self.list_matches(organization_id=organization_id, run_id=run_id)
        csv_text = self.build_csv(matches)
        filename = f"reconciliation_{run_row.period}.csv"
        return run_row, filename, csv_text
