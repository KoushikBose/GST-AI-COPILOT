"""Deterministic GST calculation and GSTIN validation endpoints.

These never touch the LLM — they're a thin HTTP layer over
`app.rules.gst_calculator` and `app.rules.gstin_validator`, kept separate
from `/chat` precisely so a caller who wants a guaranteed-deterministic
result doesn't have to go through agent routing at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db_session
from app.models.audit import AuditLog
from app.models.gst_transaction import TaxCalculation
from app.rules.gst_calculator import GSTCalculator
from app.rules.gstin_validator import validate_gstin
from app.schemas.gst import (
    GSTCalculateRequest,
    GSTCalculateResponse,
    GSTINValidateRequest,
    GSTINValidateResponse,
)
from app.security.dependencies import CurrentMembership, get_current_membership

router = APIRouter()


@router.post("/calculate", response_model=GSTCalculateResponse)
async def calculate_gst(
    body: GSTCalculateRequest,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> GSTCalculateResponse:
    settings = get_settings()
    calculator = GSTCalculator(rules_version=settings.gst_rules_version)
    result = calculator.calculate(
        taxable_value=body.taxable_value,
        gst_rate=body.gst_rate,
        transaction_type=body.transaction_type,
        cess_rate=body.cess_rate,
    )

    session.add(
        TaxCalculation(
            organization_id=membership.organization_id,
            rules_version=result.rules_version,
            input_payload=body.model_dump(mode="json"),
            result_payload=result.as_dict(),
            requested_by=membership.user_id,
        )
    )
    session.add(
        AuditLog(
            organization_id=membership.organization_id,
            actor_user_id=membership.user_id,
            action="gst.calculate",
            entity_type="tax_calculation",
            metadata_json={"rules_version": result.rules_version},
        )
    )
    await session.commit()

    return GSTCalculateResponse(**result.as_dict())


@router.post("/validate", response_model=GSTINValidateResponse)
async def validate_gstin_endpoint(
    body: GSTINValidateRequest,
    membership: CurrentMembership = Depends(get_current_membership),
) -> GSTINValidateResponse:
    result = validate_gstin(body.gstin)
    return GSTINValidateResponse(
        is_valid=result.is_valid,
        gstin=result.gstin,
        state_code=result.state_code,
        pan=result.pan,
        errors=result.errors,
    )
