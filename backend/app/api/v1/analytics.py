"""Read-only analytics endpoints powering the analytics dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schemas.analytics import (
    AgentMetricsOut,
    ComplianceAnalyticsOut,
    GstTrendPoint,
    ITCSummaryOut,
    OverviewOut,
)
from app.security.dependencies import CurrentMembership, get_current_membership
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/overview", response_model=OverviewOut)
async def analytics_overview(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> OverviewOut:
    service = AnalyticsService(session)
    return OverviewOut(**await service.overview(membership.organization_id))


@router.get("/gst-trend", response_model=list[GstTrendPoint])
async def analytics_gst_trend(
    months: int = Query(default=12, ge=1, le=36),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[GstTrendPoint]:
    service = AnalyticsService(session)
    return [
        GstTrendPoint(**row)
        for row in await service.gst_trend(membership.organization_id, months=months)
    ]


@router.get("/compliance", response_model=ComplianceAnalyticsOut)
async def analytics_compliance(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ComplianceAnalyticsOut:
    service = AnalyticsService(session)
    return ComplianceAnalyticsOut(**await service.compliance(membership.organization_id))


@router.get("/agents", response_model=AgentMetricsOut)
async def analytics_agents(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> AgentMetricsOut:
    service = AnalyticsService(session)
    return AgentMetricsOut(**await service.agent_metrics(membership.organization_id))


@router.get("/itc", response_model=ITCSummaryOut)
async def analytics_itc(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ITCSummaryOut:
    service = AnalyticsService(session)
    return ITCSummaryOut(**await service.itc_summary(membership.organization_id))
