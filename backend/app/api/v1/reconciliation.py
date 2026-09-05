"""GSTR-2A/2B reconciliation endpoints.

Upload a GSTR-2A/2B CSV export downloaded from the GST portal, reconcile it
deterministically against the period's purchase invoices, and review
matched / mismatched / missing rows. No data is fetched from the GSTN —
this is not a live portal integration.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models.rbac import ADMIN_ROLES, OrgRole
from app.models.reconciliation import ReconciliationMatchStatus, ReconciliationSource
from app.schemas.reconciliation import (
    Gstr2bUploadResponse,
    ReconciliationMatchOut,
    ReconciliationRunOut,
    RunReconciliationRequest,
)
from app.security.dependencies import CurrentMembership, get_current_membership, require_roles
from app.security.file_validation import validate_upload
from app.services.reconciliation_service import ReconciliationService

router = APIRouter()

_PREPARER_ROLES = (*ADMIN_ROLES, OrgRole.ACCOUNTANT, OrgRole.FINANCE_MANAGER)


@router.post("/upload", response_model=Gstr2bUploadResponse, status_code=201)
async def upload_2b_records(
    file: UploadFile = File(...),
    period: str = Form(...),
    source: ReconciliationSource = Form(ReconciliationSource.GSTR2B),
    membership: CurrentMembership = Depends(require_roles(*_PREPARER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> Gstr2bUploadResponse:
    content = await file.read()
    validate_upload(filename=file.filename or "upload.csv", content=content)

    service = ReconciliationService(session)
    rows = service.parse_csv(content)
    count = await service.import_records(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        period=period,
        source=source,
        rows=rows,
    )
    await session.commit()
    return Gstr2bUploadResponse(period=period, source=source, records_imported=count)


@router.post("/run", response_model=ReconciliationRunOut, status_code=201)
async def run_reconciliation(
    body: RunReconciliationRequest,
    membership: CurrentMembership = Depends(require_roles(*_PREPARER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationRunOut:
    service = ReconciliationService(session)
    run_row = await service.run(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        period=body.period,
        source=body.source,
    )
    await session.commit()
    return ReconciliationRunOut.model_validate(run_row)


@router.get("", response_model=list[ReconciliationRunOut])
async def list_runs(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReconciliationRunOut]:
    service = ReconciliationService(session)
    runs = await service.list_runs(organization_id=membership.organization_id)
    return [ReconciliationRunOut.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=ReconciliationRunOut)
async def get_run(
    run_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationRunOut:
    service = ReconciliationService(session)
    run_row = await service.get_run(organization_id=membership.organization_id, run_id=run_id)
    return ReconciliationRunOut.model_validate(run_row)


@router.get("/{run_id}/matches", response_model=list[ReconciliationMatchOut])
async def list_matches(
    run_id: uuid.UUID,
    status: ReconciliationMatchStatus | None = Query(None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[ReconciliationMatchOut]:
    service = ReconciliationService(session)
    matches = await service.list_matches(
        organization_id=membership.organization_id, run_id=run_id, status=status
    )
    return [ReconciliationMatchOut.model_validate(m) for m in matches]


@router.get("/{run_id}/export")
async def export_run(
    run_id: uuid.UUID,
    membership: CurrentMembership = Depends(require_roles(*_PREPARER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    service = ReconciliationService(session)
    _run, filename, csv_text = await service.export(
        organization_id=membership.organization_id, run_id=run_id
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
