"""Invoice AI Agent: OCR/text extraction -> LLM structured field extraction
(with per-field confidence) -> normalization -> persistence.

    Upload -> load_document (OCR if scanned) -> LLM extraction -> normalize
    -> Invoice/InvoiceItem/InvoiceTax rows -> (compliance check runs
    separately, see ComplianceService, using the deterministic rule engine)

The LLM's role is strictly extraction — turning unstructured invoice text
into structured fields with a confidence score per field. It never performs
GST arithmetic; that stays with `GSTCalculator`, invoked downstream by the
compliance/ITC services against what was extracted here.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal, InvalidOperation

import orjson

from app.core.errors import AppError
from app.core.logging import get_logger
from app.ingestion.loaders import load_document
from app.llm.base import ChatMessage, LLMProvider
from app.models.invoice import (
    Invoice,
    InvoiceDirection,
    InvoiceItem,
    InvoiceStatus,
    InvoiceTax,
    TransactionScope,
)
from app.storage.object_storage import ObjectStorage

logger = get_logger(__name__)

_EXTRACTION_SYSTEM_PROMPT = """You extract structured data from an Indian GST invoice's \
text content. Output ONLY a JSON object, no other text, matching this exact shape:

{
  "invoice_number": {"value": string|null, "confidence": number},
  "invoice_date": {"value": "YYYY-MM-DD"|null, "confidence": number},
  "supplier_name": {"value": string|null, "confidence": number},
  "supplier_gstin": {"value": string|null, "confidence": number},
  "buyer_name": {"value": string|null, "confidence": number},
  "buyer_gstin": {"value": string|null, "confidence": number},
  "place_of_supply": {"value": string|null, "confidence": number},
  "transaction_scope": {
    "value": "intra_state"|"inter_state"|"export"|"sez_supply"|"exempt"|"nil_rated"|null,
    "confidence": number
  },
  "items": [
    {
      "description": string|null,
      "hsn_sac": string|null,
      "quantity": number|null,
      "unit_price": number|null,
      "taxable_value": number,
      "gst_rate": number,
      "cgst": number,
      "sgst": number,
      "igst": number,
      "cess": number
    }
  ]
}

Rules:
- confidence is your own certainty (0.0-1.0) that the extracted value is correct.
- If a field cannot be found in the text, use null for its value and a low confidence.
- Numeric amounts must be plain numbers (no currency symbols, no commas).
- Extract every line item found in the invoice.
"""


def _to_decimal(value, default: Decimal | None = Decimal("0")) -> Decimal | None:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


class InvoiceExtractionService:
    def __init__(self, *, llm: LLMProvider, storage: ObjectStorage) -> None:
        self.llm = llm
        self.storage = storage

    async def extract_from_bytes(
        self,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
        direction: InvoiceDirection,
        organization_id: uuid.UUID,
        uploaded_by: uuid.UUID | None,
        bucket: str,
    ) -> Invoice:
        invoice = Invoice(
            organization_id=organization_id,
            direction=direction,
            status=InvoiceStatus.PROCESSING,
            created_by=uploaded_by,
            currency="INR",
        )
        return await self.extract_into(
            invoice, content=content, filename=filename, mime_type=mime_type, bucket=bucket
        )

    async def extract_into(
        self,
        invoice: Invoice,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
        bucket: str | None = None,
    ) -> Invoice:
        """Run storage + OCR + LLM extraction against an *existing* Invoice
        row, mutating it in place. Used by the async upload path so the HTTP
        request returns immediately with a ``processing`` invoice."""
        bucket = bucket or self.storage.bucket_for("invoices")
        content_hash = hashlib.sha256(content).hexdigest()
        invoice.file_hash = content_hash
        invoice.status = InvoiceStatus.PROCESSING
        storage_key = f"{invoice.direction.value}/{content_hash}/{filename}"
        try:
            self.storage.upload_bytes(
                bucket=bucket, key=storage_key, data=content, content_type=mime_type
            )
        except Exception as exc:  # noqa: BLE001 - storage outage must not lose the row
            logger.error("invoice_storage_upload_failed", error=str(exc))

        try:
            loaded = load_document(content=content, mime_type=mime_type, filename=filename)
        except AppError as exc:
            # Unsupported type, or a dependency the document needs is missing
            # (e.g. OCR engine unavailable for a scanned invoice). Record the
            # failure on the invoice rather than 500-ing the upload.
            invoice.status = InvoiceStatus.FAILED
            invoice.extracted_fields = {"error": exc.message}
            return invoice
        except Exception as exc:  # noqa: BLE001 - never fail the upload on a loader bug
            logger.error("invoice_document_load_failed", error=str(exc))
            invoice.status = InvoiceStatus.FAILED
            invoice.extracted_fields = {"error": f"Could not read this file: {exc}"}
            return invoice

        text = loaded.full_text
        if not text.strip():
            invoice.status = InvoiceStatus.FAILED
            invoice.extracted_fields = {"error": "No text could be extracted from this invoice."}
            return invoice

        avg_ocr_confidence = self._average_ocr_confidence(loaded)

        try:
            extracted = await self._extract_fields_via_llm(text)
        except Exception as exc:
            logger.error("invoice_llm_extraction_failed", error=str(exc))
            invoice.status = InvoiceStatus.NEEDS_REVIEW
            invoice.extracted_fields = {"error": f"AI extraction failed: {exc}"}
            invoice.ocr_confidence = avg_ocr_confidence
            return invoice

        self._apply_extracted_fields(invoice, extracted)
        invoice.ocr_confidence = avg_ocr_confidence
        invoice.status = InvoiceStatus.EXTRACTED
        return invoice

    def _average_ocr_confidence(self, loaded) -> Decimal | None:
        ocr_pages = [p for p in loaded.pages if p.was_ocr and p.ocr_confidence is not None]
        if not ocr_pages:
            return None
        avg = sum(p.ocr_confidence for p in ocr_pages) / len(ocr_pages)
        return Decimal(str(round(avg, 3)))

    async def _extract_fields_via_llm(self, text: str) -> dict:
        # Cap input length to keep prompts bounded for very large invoices.
        truncated = text[:12000]
        response = await self.llm.chat(
            [
                ChatMessage(role="system", content=_EXTRACTION_SYSTEM_PROMPT),
                ChatMessage(role="user", content=f"Invoice text:\n\n{truncated}"),
            ],
            temperature=0.0,
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").removeprefix("json").strip()
        return orjson.loads(raw)

    def _apply_extracted_fields(self, invoice: Invoice, extracted: dict) -> None:
        def field_value(name: str):
            entry = extracted.get(name) or {}
            return entry.get("value") if isinstance(entry, dict) else None

        invoice.invoice_number = field_value("invoice_number")
        invoice.invoice_date = field_value("invoice_date")
        invoice.supplier_name = field_value("supplier_name")
        invoice.supplier_gstin = (field_value("supplier_gstin") or "").upper() or None
        invoice.buyer_name = field_value("buyer_name")
        invoice.buyer_gstin = (field_value("buyer_gstin") or "").upper() or None
        invoice.place_of_supply = field_value("place_of_supply")

        scope_value = field_value("transaction_scope")
        try:
            invoice.transaction_scope = TransactionScope(scope_value) if scope_value else None
        except ValueError:
            invoice.transaction_scope = None

        invoice.extracted_fields = {
            k: v for k, v in extracted.items() if k != "items" and isinstance(v, dict)
        }

        items_data = extracted.get("items") or []
        taxable_total = Decimal("0")
        cgst_total = Decimal("0")
        sgst_total = Decimal("0")
        igst_total = Decimal("0")
        cess_total = Decimal("0")

        for i, item_data in enumerate(items_data, start=1):
            taxable_value = _to_decimal(item_data.get("taxable_value"))
            cgst = _to_decimal(item_data.get("cgst"))
            sgst = _to_decimal(item_data.get("sgst"))
            igst = _to_decimal(item_data.get("igst"))
            cess = _to_decimal(item_data.get("cess"))
            line_total = taxable_value + cgst + sgst + igst + cess

            invoice.items.append(
                InvoiceItem(
                    line_number=i,
                    description=item_data.get("description"),
                    hsn_sac=item_data.get("hsn_sac"),
                    quantity=_to_decimal(item_data.get("quantity"), default=None),
                    unit_price=_to_decimal(item_data.get("unit_price"), default=None),
                    taxable_value=taxable_value,
                    gst_rate=_to_decimal(item_data.get("gst_rate")),
                    cess_rate=Decimal("0"),
                    cgst=cgst,
                    sgst=sgst,
                    igst=igst,
                    cess=cess,
                    line_total=line_total,
                )
            )
            taxable_total += taxable_value
            cgst_total += cgst
            sgst_total += sgst
            igst_total += igst
            cess_total += cess

        invoice.taxable_value = taxable_total
        invoice.total_tax = cgst_total + sgst_total + igst_total + cess_total
        invoice.grand_total = taxable_total + invoice.total_tax

        for tax_type, amount in (
            ("cgst", cgst_total),
            ("sgst", sgst_total),
            ("igst", igst_total),
            ("cess", cess_total),
        ):
            if amount:
                invoice.taxes.append(InvoiceTax(tax_type=tax_type, amount=amount))
