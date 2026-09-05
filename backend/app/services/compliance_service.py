"""Compliance Agent: runs the deterministic invoice validation rule engine
against a persisted invoice and records the result.

AI explanation of *why* a rule fired (in plain language) is layered on top
via `explain_compliance_issues` — the rules themselves are 100%
deterministic and the LLM is never in the decision path for what counts as
a compliance issue.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMProvider
from app.models.compliance import ComplianceCheck, ComplianceIssue, ComplianceSeverity
from app.models.invoice import Invoice
from app.rules.invoice_validation import (
    InvoiceLineItemInput,
    InvoiceValidationInput,
    validate_invoice,
)

logger = get_logger(__name__)

_EXPLAIN_PROMPT = (
    "You explain GST invoice compliance issues to a non-technical business "
    "owner in one or two plain-English sentences per issue. You are given "
    "the rule code and message; do not invent additional issues or change "
    "the severity. If you are unsure what an issue means, say so plainly."
)


class ComplianceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _is_duplicate_invoice_number(
        self, *, organization_id: uuid.UUID, invoice_number: str | None, exclude_id: uuid.UUID
    ) -> bool:
        if not invoice_number:
            return False
        stmt = select(Invoice.id).where(
            Invoice.organization_id == organization_id,
            Invoice.invoice_number == invoice_number,
            Invoice.id != exclude_id,
        )
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def run_check(self, invoice: Invoice) -> ComplianceCheck:
        is_duplicate = await self._is_duplicate_invoice_number(
            organization_id=invoice.organization_id,
            invoice_number=invoice.invoice_number,
            exclude_id=invoice.id,
        )

        validation_input = InvoiceValidationInput(
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            supplier_gstin=invoice.supplier_gstin,
            buyer_gstin=invoice.buyer_gstin,
            place_of_supply=invoice.place_of_supply,
            transaction_scope=invoice.transaction_scope,
            items=[
                InvoiceLineItemInput(
                    description=item.description,
                    hsn_sac=item.hsn_sac,
                    taxable_value=item.taxable_value,
                    gst_rate=item.gst_rate,
                    cgst=item.cgst,
                    sgst=item.sgst,
                    igst=item.igst,
                    cess=item.cess,
                )
                for item in invoice.items
            ],
            declared_taxable_value=invoice.taxable_value,
            is_duplicate_invoice_number=is_duplicate,
        )

        report = validate_invoice(validation_input)
        settings = get_settings()

        check = ComplianceCheck(
            organization_id=invoice.organization_id,
            invoice_id=invoice.id,
            score=report.score,
            passed_checks=report.passed_checks,
            total_checks=report.total_checks,
            rules_version=settings.gst_rules_version,
            summary={"status": report.status},
        )
        check.issues = [
            ComplianceIssue(
                severity=ComplianceSeverity(issue.severity.value),
                rule_code=issue.rule_code,
                field=issue.field,
                message=issue.message,
                recommendation=issue.recommendation,
            )
            for issue in report.issues
        ]
        self.session.add(check)
        await self.session.flush()
        return check

    async def explain_issues(self, llm: LLMProvider, check: ComplianceCheck) -> str:
        """Optional plain-language summary of a compliance check's issues,
        generated from (not in place of) the deterministic results above."""
        if not check.issues:
            return "No compliance issues were found on this invoice."

        issue_lines = "\n".join(
            f"- [{i.severity.value.upper()}] {i.rule_code}: {i.message}" for i in check.issues
        )
        try:
            response = await llm.chat(
                [
                    ChatMessage(role="system", content=_EXPLAIN_PROMPT),
                    ChatMessage(role="user", content=issue_lines),
                ],
                temperature=0.1,
            )
            return response.content.strip()
        except Exception as exc:
            logger.warning("compliance_explanation_failed", error=str(exc))
            return issue_lines
