"""Pydantic schemas for the analytics API.

Kept intentionally permissive (`dict` / `list[dict]`) — these are read-only
aggregation payloads shaped by `AnalyticsService`, and pinning every nested
field here would just duplicate that shape with no safety gain.
"""

from __future__ import annotations

from pydantic import BaseModel


class OverviewOut(BaseModel):
    total_invoices: int
    total_tax: float
    invoices_by_direction: dict
    invoices_needing_review: int
    avg_compliance_score: float
    pending_approvals: int
    agent_runs_by_status: dict
    itc_records_needing_review: int


class GstTrendPoint(BaseModel):
    period: str
    outward_tax: float
    inward_tax: float
    outward_taxable: float
    inward_taxable: float
    net_tax: float
    invoice_count: int


class ComplianceAnalyticsOut(BaseModel):
    avg_score: float
    total_checks: int
    passed_checks: int
    total_rule_evaluations: int
    issues_by_severity: list[dict]
    score_trend: list[dict]


class AgentMetricsOut(BaseModel):
    total_runs: int
    escalation_rate: float
    by_status: dict
    by_intent: list[dict]
    runs_trend: list[dict]


class ITCSummaryOut(BaseModel):
    by_status: list[dict]
