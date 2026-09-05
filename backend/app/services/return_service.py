"""Return preparation service.

Aggregates an organization's invoices for a tax period into a reviewable
GSTR-1 / GSTR-3B draft. All arithmetic is delegated to the deterministic
`app.rules.return_aggregation` module; this service only does the ORM →
plain-input adaptation, persistence, and CSV export.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.approval import Approval, ApprovalRisk, ApprovalStatus, ApprovalType
from app.models.audit import AuditLog
from app.models.gst_return import GSTReturn, ReturnStatus, ReturnType
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.rules.return_aggregation import (
    ReturnInvoiceInput,
    ReturnLineInput,
    build_gstr1,
    build_gstr3b,
    gstr1_to_csv_rows,
)
from app.storage.object_storage import ObjectStorage

logger = get_logger(__name__)

_PERIOD_LEN = 7  # "YYYY-MM"
_EXCLUDED_STATUSES = {InvoiceStatus.FAILED, InvoiceStatus.REJECTED}


def _validate_period(period: str) -> None:
    if len(period) != _PERIOD_LEN or period[4] != "-":
        raise ValidationFailedError("period must be in 'YYYY-MM' format.")
    year, month = period[:4], period[5:]
    if not (year.isdigit() and month.isdigit() and 1 <= int(month) <= 12):
        raise ValidationFailedError("period must be a valid calendar month, e.g. '2026-01'.")


class ReturnService:
    def __init__(self, session: AsyncSession, *, storage: ObjectStorage | None = None) -> None:
        self.session = session
        self.storage = storage

    async def _load_period_invoices(
        self, *, organization_id: uuid.UUID, period: str
    ) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(
                Invoice.organization_id == organization_id,
                Invoice.invoice_date.is_not(None),
                Invoice.invoice_date.like(f"{period}-%"),
                Invoice.status.not_in(_EXCLUDED_STATUSES),
            )
            .options(selectinload(Invoice.items))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _to_inputs(invoices: list[Invoice]) -> list[ReturnInvoiceInput]:
        inputs: list[ReturnInvoiceInput] = []
        for inv in invoices:
            is_sales = inv.direction == InvoiceDirection.SALES
            counterparty_gstin = inv.buyer_gstin if is_sales else inv.supplier_gstin
            counterparty_name = inv.buyer_name if is_sales else inv.supplier_name
            inputs.append(
                ReturnInvoiceInput(
                    direction="sales" if is_sales else "purchase",
                    invoice_number=inv.invoice_number,
                    invoice_date=inv.invoice_date,
                    counterparty_name=counterparty_name,
                    counterparty_gstin=counterparty_gstin,
                    place_of_supply=inv.place_of_supply,
                    lines=[
                        ReturnLineInput(
                            taxable_value=item.taxable_value or Decimal("0"),
                            gst_rate=item.gst_rate or Decimal("0"),
                            cgst=item.cgst or Decimal("0"),
                            sgst=item.sgst or Decimal("0"),
                            igst=item.igst or Decimal("0"),
                            cess=item.cess or Decimal("0"),
                        )
                        for item in inv.items
                    ],
                )
            )
        return inputs

    async def generate(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        return_type: ReturnType,
        period: str,
    ) -> GSTReturn:
        _validate_period(period)
        settings = get_settings()

        invoices = await self._load_period_invoices(
            organization_id=organization_id, period=period
        )
        inputs = self._to_inputs(invoices)

        if return_type == ReturnType.GSTR1:
            summary = build_gstr1(period, inputs).as_dict()
            relevant = [i for i in inputs if i.direction == "sales"]
            total_taxable = Decimal(summary["totals"]["taxable_value"])
            total_tax = Decimal(summary["totals"]["total_tax"])
        else:
            summary = build_gstr3b(period, inputs).as_dict()
            relevant = inputs
            total_taxable = Decimal(summary["outward_taxable_supplies"]["taxable_value"])
            total_tax = Decimal(summary["net_tax_payable"]["total_tax"])

        existing = await self.session.execute(
            select(GSTReturn).where(
                GSTReturn.organization_id == organization_id,
                GSTReturn.return_type == return_type,
                GSTReturn.period == period,
            )
        )
        gst_return = existing.scalar_one_or_none()
        if gst_return is None:
            gst_return = GSTReturn(
                organization_id=organization_id,
                return_type=return_type,
                period=period,
                rules_version=settings.gst_rules_version,
            )
            self.session.add(gst_return)
        elif gst_return.status in (ReturnStatus.APPROVED, ReturnStatus.FILED_EXTERNALLY):
            raise ValidationFailedError(
                "This return has already been approved and can no longer be regenerated."
            )

        gst_return.status = ReturnStatus.GENERATED
        gst_return.invoice_count = len(relevant)
        gst_return.total_taxable_value = total_taxable
        gst_return.total_tax = total_tax
        gst_return.summary = summary
        gst_return.generated_by = user_id
        gst_return.approved_by = None
        gst_return.review_notes = None
        gst_return.export_storage_key = None

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="return.generate",
                entity_type="gst_return",
                entity_id=str(gst_return.id),
                metadata_json={"return_type": return_type.value, "period": period},
            )
        )
        await self.session.flush()
        logger.info(
            "return_generated",
            return_type=return_type.value,
            period=period,
            invoice_count=len(relevant),
        )
        return gst_return

    async def get(self, *, organization_id: uuid.UUID, return_id: uuid.UUID) -> GSTReturn:
        result = await self.session.execute(
            select(GSTReturn).where(
                GSTReturn.id == return_id, GSTReturn.organization_id == organization_id
            )
        )
        gst_return = result.scalar_one_or_none()
        if gst_return is None:
            raise NotFoundError("Return not found.")
        return gst_return

    async def list_returns(self, *, organization_id: uuid.UUID) -> list[GSTReturn]:
        result = await self.session.execute(
            select(GSTReturn)
            .where(GSTReturn.organization_id == organization_id)
            .order_by(GSTReturn.period.desc(), GSTReturn.return_type)
        )
        return list(result.scalars().all())

    async def submit_for_review(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID, return_id: uuid.UUID
    ) -> tuple[GSTReturn, Approval]:
        gst_return = await self.get(organization_id=organization_id, return_id=return_id)
        if gst_return.status not in (ReturnStatus.GENERATED, ReturnStatus.DRAFT):
            raise ValidationFailedError(
                f"A return in '{gst_return.status.value}' state cannot be submitted for review."
            )
        gst_return.status = ReturnStatus.UNDER_REVIEW

        approval = Approval(
            organization_id=organization_id,
            approval_type=ApprovalType.RETURN_PREPARATION,
            risk=ApprovalRisk.HIGH,
            status=ApprovalStatus.PENDING,
            entity_type="gst_return",
            entity_id=str(gst_return.id),
            ai_recommendation={
                "return_type": gst_return.return_type.value,
                "period": gst_return.period,
                "invoice_count": gst_return.invoice_count,
                "total_tax": str(gst_return.total_tax),
            },
            evidence=[],
            assigned_to=None,
        )
        self.session.add(approval)
        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="return.submit_for_review",
                entity_type="gst_return",
                entity_id=str(gst_return.id),
                metadata_json={},
            )
        )
        await self.session.flush()
        return gst_return, approval

    def build_csv(self, gst_return: GSTReturn) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        summary = gst_return.summary or {}

        if gst_return.return_type == ReturnType.GSTR1:
            from app.rules.return_aggregation import GSTR1Summary

            reconstructed = GSTR1Summary(
                period=summary.get("period", gst_return.period),
                b2b=summary.get("b2b", []),
                b2c=summary.get("b2c", []),
                rate_wise=summary.get("rate_wise", []),
                totals=summary.get("totals", {}),
            )
            for row in gstr1_to_csv_rows(reconstructed):
                writer.writerow(row)
        else:
            writer.writerow(
                ["section", "taxable_value", "igst", "cgst", "sgst", "cess", "total_tax"]
            )
            for label, key in (
                ("Outward taxable supplies", "outward_taxable_supplies"),
                ("Eligible ITC", "eligible_itc"),
                ("Net tax payable", "net_tax_payable"),
            ):
                block = summary.get(key, {})
                writer.writerow(
                    [
                        label,
                        block.get("taxable_value", ""),
                        block.get("igst", ""),
                        block.get("cgst", ""),
                        block.get("sgst", ""),
                        block.get("cess", ""),
                        block.get("total_tax", ""),
                    ]
                )
        return buffer.getvalue()

    async def export(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID, return_id: uuid.UUID
    ) -> tuple[GSTReturn, str, str]:
        """Returns (return, filename, csv_text). Persists an export marker."""
        gst_return = await self.get(organization_id=organization_id, return_id=return_id)
        csv_text = self.build_csv(gst_return)
        filename = f"{gst_return.return_type.value}_{gst_return.period}.csv"

        if self.storage is not None:
            key = f"returns/{organization_id}/{return_id}/{filename}"
            try:
                self.storage.upload_bytes(
                    bucket=self.storage.bucket_for("exports"),
                    key=key,
                    data=csv_text.encode("utf-8"),
                    content_type="text/csv",
                )
                gst_return.export_storage_key = key
            except Exception as exc:  # noqa: BLE001 - export must not fail on storage
                logger.warning("return_export_storage_failed", error=str(exc))

        if gst_return.status == ReturnStatus.APPROVED:
            gst_return.status = ReturnStatus.EXPORTED

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="return.export",
                entity_type="gst_return",
                entity_id=str(gst_return.id),
                metadata_json={"filename": filename},
            )
        )
        await self.session.flush()
        return gst_return, filename, csv_text
