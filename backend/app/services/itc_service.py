"""ITC Assistant: deterministic eligibility pre-checks + RAG-grounded
explanation of what still needs verification.

Real-world ITC eligibility depends on facts a single invoice can never
fully establish on its own — whether goods/services were actually received,
whether the supplier has filed their return and paid the tax, and the
Section 17(5) blocked-credit categories. Because of that, this service
never asserts unconditional eligibility: a clean invoice comes back
REVIEW_REQUIRED with the specific open questions listed, not ELIGIBLE.
Only clear, invoice-level disqualifiers (invalid supplier GSTIN, no tax
charged, missing mandatory fields) produce a deterministic INELIGIBLE.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.models.gst_transaction import ITCRecord, ITCStatus
from app.models.invoice import Invoice
from app.rag.embeddings import EmbeddingProvider
from app.rag.pipeline import answer_gst_question
from app.rules.gstin_validator import validate_gstin

logger = get_logger(__name__)

_STANDARD_OPEN_QUESTIONS = [
    "Goods or services under this invoice have actually been received.",
    "The supplier has filed their GSTR-1/GSTR-3B and the tax has reached the government.",
    "The expense does not fall under a Section 17(5) blocked-credit category "
    "(e.g. motor vehicles, food/beverages, club memberships) for this business.",
    "Payment to the supplier is made within 180 days of the invoice date.",
]


class ITCService:
    def __init__(
        self, session: AsyncSession, *, llm: LLMProvider, embedding_provider: EmbeddingProvider
    ) -> None:
        self.session = session
        self.llm = llm
        self.embeddings = embedding_provider

    def _deterministic_disqualifiers(self, invoice: Invoice) -> list[str]:
        reasons: list[str] = []

        gstin_result = validate_gstin(invoice.supplier_gstin)
        if not gstin_result.is_valid:
            reasons.append(
                f"Supplier GSTIN is missing or invalid: {'; '.join(gstin_result.errors)}."
            )

        total_tax = invoice.total_tax or Decimal("0")
        if total_tax <= 0:
            reasons.append("No GST was charged on this invoice, so there is no credit to claim.")

        if not invoice.invoice_number:
            reasons.append("Invoice number is missing — required documentary evidence for ITC.")

        if not invoice.items:
            reasons.append("No line items were extracted from this invoice.")

        return reasons

    async def analyze(self, invoice: Invoice) -> ITCRecord:
        disqualifiers = self._deterministic_disqualifiers(invoice)

        if disqualifiers:
            record = ITCRecord(
                organization_id=invoice.organization_id,
                invoice_id=invoice.id,
                status=ITCStatus.INELIGIBLE,
                eligible_amount=Decimal("0"),
                confidence=Decimal("0.900"),
                reasons=disqualifiers,
                missing_evidence=[],
                citations=[],
                requires_human_review=True,
            )
        else:
            rag_result = await answer_gst_question(
                llm=self.llm,
                embedding_provider=self.embeddings,
                question=(
                    "What are the conditions for claiming input tax credit under GST, "
                    "and what documentation is required?"
                ),
                tenant_id=str(invoice.organization_id),
            )
            record = ITCRecord(
                organization_id=invoice.organization_id,
                invoice_id=invoice.id,
                status=ITCStatus.REVIEW_REQUIRED,
                eligible_amount=invoice.total_tax,
                confidence=Decimal(str(round(rag_result.confidence, 3))),
                reasons=[
                    "Invoice-level checks passed (valid supplier GSTIN, tax charged, "
                    "mandatory fields present).",
                    *_STANDARD_OPEN_QUESTIONS,
                ],
                missing_evidence=[
                    "Proof of receipt of goods/services "
                    "(e.g. goods receipt note, delivery challan).",
                    "Confirmation the supplier has filed their GST return for this period.",
                ],
                citations=[
                    {
                        "document": c.document,
                        "section": c.section,
                        "page": c.page,
                        "relevance_score": c.relevance_score,
                    }
                    for c in rag_result.sources
                ],
                requires_human_review=True,
            )

        self.session.add(record)
        await self.session.flush()
        return record
