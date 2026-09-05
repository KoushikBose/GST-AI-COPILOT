"""Read-only analytics aggregations.

Every method is a grouped SQL query scoped to one organization — no LLM, no
mutation. The frontend analytics dashboard is a thin renderer over these.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.approval import Approval, ApprovalStatus
from app.models.compliance import ComplianceCheck, ComplianceIssue
from app.models.gst_transaction import ITCRecord
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus

_D0 = Decimal("0")


def _num(value) -> float:  # noqa: ANN001
    if value is None:
        return 0.0
    return float(value)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def overview(self, organization_id: uuid.UUID) -> dict:
        inv_rows = (
            await self.session.execute(
                select(
                    Invoice.direction,
                    func.count(),
                    func.coalesce(func.sum(Invoice.taxable_value), 0),
                    func.coalesce(func.sum(Invoice.total_tax), 0),
                )
                .where(Invoice.organization_id == organization_id)
                .group_by(Invoice.direction)
            )
        ).all()

        by_direction = {
            d.value: {"count": 0, "taxable_value": 0.0, "total_tax": 0.0}
            for d in InvoiceDirection
        }
        for direction, count, taxable, tax in inv_rows:
            by_direction[direction.value] = {
                "count": count,
                "taxable_value": _num(taxable),
                "total_tax": _num(tax),
            }

        needs_review = (
            await self.session.execute(
                select(func.count())
                .select_from(Invoice)
                .where(
                    Invoice.organization_id == organization_id,
                    Invoice.status == InvoiceStatus.NEEDS_REVIEW,
                )
            )
        ).scalar_one()

        avg_compliance = (
            await self.session.execute(
                select(func.avg(ComplianceCheck.score)).where(
                    ComplianceCheck.organization_id == organization_id
                )
            )
        ).scalar_one()

        pending_approvals = (
            await self.session.execute(
                select(func.count())
                .select_from(Approval)
                .where(
                    Approval.organization_id == organization_id,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
        ).scalar_one()

        agent_rows = (
            await self.session.execute(
                select(AgentRun.status, func.count())
                .where(AgentRun.organization_id == organization_id)
                .group_by(AgentRun.status)
            )
        ).all()
        agent_by_status = {status.value: count for status, count in agent_rows}

        itc_review = (
            await self.session.execute(
                select(func.count())
                .select_from(ITCRecord)
                .where(
                    ITCRecord.organization_id == organization_id,
                    ITCRecord.requires_human_review.is_(True),
                )
            )
        ).scalar_one()

        total_invoices = sum(v["count"] for v in by_direction.values())
        total_tax = sum(v["total_tax"] for v in by_direction.values())

        return {
            "total_invoices": total_invoices,
            "total_tax": total_tax,
            "invoices_by_direction": by_direction,
            "invoices_needing_review": needs_review,
            "avg_compliance_score": round(_num(avg_compliance), 1),
            "pending_approvals": pending_approvals,
            "agent_runs_by_status": agent_by_status,
            "itc_records_needing_review": itc_review,
        }

    async def gst_trend(self, organization_id: uuid.UUID, *, months: int = 12) -> list[dict]:
        period = func.substr(Invoice.invoice_date, 1, 7)
        rows = (
            await self.session.execute(
                select(
                    period.label("period"),
                    Invoice.direction,
                    func.coalesce(func.sum(Invoice.total_tax), 0),
                    func.coalesce(func.sum(Invoice.taxable_value), 0),
                    func.count(),
                )
                .where(
                    Invoice.organization_id == organization_id,
                    Invoice.invoice_date.is_not(None),
                )
                .group_by("period", Invoice.direction)
                .order_by("period")
            )
        ).all()

        buckets: dict[str, dict] = {}
        for p, direction, tax, taxable, count in rows:
            b = buckets.setdefault(
                p,
                {
                    "period": p,
                    "outward_tax": 0.0,
                    "inward_tax": 0.0,
                    "outward_taxable": 0.0,
                    "inward_taxable": 0.0,
                    "invoice_count": 0,
                },
            )
            if direction == InvoiceDirection.SALES:
                b["outward_tax"] = _num(tax)
                b["outward_taxable"] = _num(taxable)
            else:
                b["inward_tax"] = _num(tax)
                b["inward_taxable"] = _num(taxable)
            b["invoice_count"] += count

        ordered = [buckets[k] for k in sorted(buckets)][-months:]
        for b in ordered:
            b["net_tax"] = round(b["outward_tax"] - b["inward_tax"], 2)
        return ordered

    async def compliance(self, organization_id: uuid.UUID) -> dict:
        agg = (
            await self.session.execute(
                select(
                    func.avg(ComplianceCheck.score),
                    func.count(),
                    func.coalesce(func.sum(ComplianceCheck.passed_checks), 0),
                    func.coalesce(func.sum(ComplianceCheck.total_checks), 0),
                ).where(ComplianceCheck.organization_id == organization_id)
            )
        ).one()

        severity_rows = (
            await self.session.execute(
                select(ComplianceIssue.severity, func.count())
                .join(ComplianceCheck, ComplianceIssue.check_id == ComplianceCheck.id)
                .where(ComplianceCheck.organization_id == organization_id)
                .group_by(ComplianceIssue.severity)
            )
        ).all()

        period = func.to_char(ComplianceCheck.created_at, "YYYY-MM")
        trend_rows = (
            await self.session.execute(
                select(period.label("period"), func.avg(ComplianceCheck.score), func.count())
                .where(ComplianceCheck.organization_id == organization_id)
                .group_by("period")
                .order_by("period")
            )
        ).all()

        return {
            "avg_score": round(_num(agg[0]), 1),
            "total_checks": agg[1],
            "passed_checks": int(_num(agg[2])),
            "total_rule_evaluations": int(_num(agg[3])),
            "issues_by_severity": [
                {"severity": sev.value, "count": count} for sev, count in severity_rows
            ],
            "score_trend": [
                {"period": p, "avg_score": round(_num(avg), 1), "checks": count}
                for p, avg, count in trend_rows
            ],
        }

    async def agent_metrics(self, organization_id: uuid.UUID) -> dict:
        intent_rows = (
            await self.session.execute(
                select(
                    func.coalesce(AgentRun.intent, "UNKNOWN"),
                    func.count(),
                    func.avg(AgentRun.total_latency_ms),
                    func.avg(cast(AgentRun.confidence, Numeric)),
                )
                .where(AgentRun.organization_id == organization_id)
                .group_by(AgentRun.intent)
            )
        ).all()

        status_rows = (
            await self.session.execute(
                select(AgentRun.status, func.count())
                .where(AgentRun.organization_id == organization_id)
                .group_by(AgentRun.status)
            )
        ).all()

        total = sum(count for _, count in status_rows)
        escalated = sum(
            count for status, count in status_rows if status.value in ("escalated", "failed")
        )

        period = func.to_char(AgentRun.created_at, "YYYY-MM")
        trend_rows = (
            await self.session.execute(
                select(
                    period.label("period"),
                    func.count(),
                    func.avg(AgentRun.total_latency_ms),
                )
                .where(AgentRun.organization_id == organization_id)
                .group_by("period")
                .order_by("period")
            )
        ).all()

        return {
            "total_runs": total,
            "escalation_rate": round(escalated / total, 3) if total else 0.0,
            "by_status": {status.value: count for status, count in status_rows},
            "by_intent": [
                {
                    "intent": intent,
                    "count": count,
                    "avg_latency_ms": int(_num(latency)),
                    "avg_confidence": round(_num(conf), 3),
                }
                for intent, count, latency, conf in intent_rows
            ],
            "runs_trend": [
                {"period": p, "runs": count, "avg_latency_ms": int(_num(latency))}
                for p, count, latency in trend_rows
            ],
        }

    async def itc_summary(self, organization_id: uuid.UUID) -> dict:
        rows = (
            await self.session.execute(
                select(
                    ITCRecord.status,
                    func.count(),
                    func.coalesce(func.sum(ITCRecord.eligible_amount), 0),
                )
                .where(ITCRecord.organization_id == organization_id)
                .group_by(ITCRecord.status)
            )
        ).all()
        return {
            "by_status": [
                {
                    "status": status.value,
                    "count": count,
                    "eligible_amount": _num(amount),
                }
                for status, count, amount in rows
            ],
        }
