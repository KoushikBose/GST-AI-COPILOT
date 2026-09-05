"""Aggregates all v1 API routers.

Routers are added phase-by-phase as each subsystem is implemented; keeping
this file as the single place that wires them in makes it obvious what's
live at any point in the build.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.accounting import router as accounting_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.documents import router as documents_router
from app.api.v1.gst import router as gst_router
from app.api.v1.health import router as health_router
from app.api.v1.invoices import router as invoices_router
from app.api.v1.itc import router as itc_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.rag import router as rag_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.returns import router as returns_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(gst_router, prefix="/gst", tags=["gst"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(rag_router, prefix="/rag", tags=["rag"])
api_router.include_router(invoices_router, prefix="/invoices", tags=["invoices"])
api_router.include_router(compliance_router, prefix="/compliance", tags=["compliance"])
api_router.include_router(itc_router, prefix="/itc", tags=["itc"])
api_router.include_router(organizations_router, prefix="/organizations", tags=["organizations"])
api_router.include_router(returns_router, prefix="/returns", tags=["returns"])
api_router.include_router(
    reconciliation_router, prefix="/reconciliation", tags=["reconciliation"]
)
api_router.include_router(approvals_router, prefix="/approvals", tags=["approvals"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(accounting_router, prefix="/accounting", tags=["accounting"])
