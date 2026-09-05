"""Double-entry accounting endpoints — the "Tally-like" bookkeeping surface.

Masters (groups / ledgers), vouchers (day book), invoice → books posting,
and the financial statements (Trial Balance, Profit & Loss, Balance Sheet,
ledger statement, outstanding receivables/payables) plus CSV export.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.errors import NotFoundError
from app.models.accounting import Ledger, VoucherType
from app.models.invoice import Invoice
from app.models.rbac import ADMIN_ROLES, OrgRole
from app.schemas.accounting import (
    CreateLedgerRequest,
    CreateVoucherRequest,
    LedgerGroupOut,
    LedgerOut,
    VoucherOut,
    VoucherSummaryOut,
)
from app.security.dependencies import CurrentMembership, get_current_membership, require_roles
from app.services.accounting_service import AccountingService, EntryDraft

router = APIRouter()

_ACCOUNTANT_ROLES = (*ADMIN_ROLES, OrgRole.ACCOUNTANT, OrgRole.FINANCE_MANAGER)


def _ledger_out(ledger: Ledger) -> LedgerOut:
    return LedgerOut(
        id=ledger.id,
        name=ledger.name,
        group_id=ledger.group_id,
        group_name=ledger.group.name if ledger.group else "",
        nature=ledger.group.nature,
        opening_balance=ledger.opening_balance,
        opening_side=ledger.opening_side,
        gstin=ledger.gstin,
        is_system=ledger.is_system,
        is_active=ledger.is_active,
        notes=ledger.notes,
    )


@router.post("/initialise", response_model=list[LedgerGroupOut])
async def initialise_chart_of_accounts(
    membership: CurrentMembership = Depends(require_roles(*_ACCOUNTANT_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> list[LedgerGroupOut]:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()
    groups = await service.list_groups(membership.organization_id)
    return [LedgerGroupOut.model_validate(g) for g in groups]


@router.get("/groups", response_model=list[LedgerGroupOut])
async def list_groups(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[LedgerGroupOut]:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()
    groups = await service.list_groups(membership.organization_id)
    return [LedgerGroupOut.model_validate(g) for g in groups]


@router.get("/ledgers", response_model=list[LedgerOut])
async def list_ledgers(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[LedgerOut]:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()
    ledgers = await service.list_ledgers(membership.organization_id)
    return [_ledger_out(lg) for lg in ledgers]


@router.post("/ledgers", response_model=LedgerOut, status_code=201)
async def create_ledger(
    body: CreateLedgerRequest,
    membership: CurrentMembership = Depends(require_roles(*_ACCOUNTANT_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> LedgerOut:
    service = AccountingService(session)
    ledger = await service.create_ledger(
        organization_id=membership.organization_id,
        name=body.name,
        group_id=body.group_id,
        opening_balance=body.opening_balance,
        opening_side=body.opening_side,
        gstin=body.gstin,
        notes=body.notes,
    )
    await session.commit()
    return _ledger_out(ledger)


@router.get("/ledgers/{ledger_id}/statement")
async def ledger_statement(
    ledger_id: uuid.UUID,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AccountingService(session)
    return await service.ledger_statement(
        organization_id=membership.organization_id,
        ledger_id=ledger_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/vouchers", response_model=list[VoucherSummaryOut])
async def list_vouchers(
    voucher_type: VoucherType | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[VoucherSummaryOut]:
    service = AccountingService(session)
    vouchers = await service.list_vouchers(
        organization_id=membership.organization_id,
        voucher_type=voucher_type,
        date_from=date_from,
        date_to=date_to,
    )
    return [VoucherSummaryOut.model_validate(v) for v in vouchers]


@router.post("/vouchers", response_model=VoucherOut, status_code=201)
async def create_voucher(
    body: CreateVoucherRequest,
    membership: CurrentMembership = Depends(require_roles(*_ACCOUNTANT_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> VoucherOut:
    service = AccountingService(session)
    voucher = await service.create_voucher(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        voucher_type=body.voucher_type,
        voucher_date=body.date,
        entries=[
            EntryDraft(e.ledger_id, e.side, e.amount, e.narration) for e in body.entries
        ],
        narration=body.narration,
        reference=body.reference,
    )
    await session.commit()
    return VoucherOut.model_validate(voucher)


@router.get("/vouchers/{voucher_id}", response_model=VoucherOut)
async def get_voucher(
    voucher_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> VoucherOut:
    service = AccountingService(session)
    voucher = await service.get_voucher(
        organization_id=membership.organization_id, voucher_id=voucher_id
    )
    return VoucherOut.model_validate(voucher)


@router.post("/invoices/{invoice_id}/post", response_model=VoucherOut, status_code=201)
async def post_invoice_to_books(
    invoice_id: uuid.UUID,
    membership: CurrentMembership = Depends(require_roles(*_ACCOUNTANT_ROLES)),
    session: AsyncSession = Depends(get_db_session),
) -> VoucherOut:
    result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.organization_id == membership.organization_id)
        .options(selectinload(Invoice.items))
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found.")

    service = AccountingService(session)
    voucher = await service.post_invoice(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        invoice=invoice,
    )
    await session.commit()
    return VoucherOut.model_validate(voucher)


# ---- financial statements ----


@router.get("/reports/trial-balance")
async def trial_balance(
    as_on: str | None = Query(default=None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()
    return await service.trial_balance(organization_id=membership.organization_id, as_on=as_on)


@router.get("/reports/profit-loss")
async def profit_loss(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()
    return await service.profit_and_loss(
        organization_id=membership.organization_id, date_from=date_from, date_to=date_to
    )


@router.get("/reports/balance-sheet")
async def balance_sheet(
    as_on: str | None = Query(default=None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()
    return await service.balance_sheet(organization_id=membership.organization_id, as_on=as_on)


@router.get("/reports/day-book", response_model=list[VoucherSummaryOut])
async def day_book(
    date_from: str | None = None,
    date_to: str | None = None,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[VoucherSummaryOut]:
    service = AccountingService(session)
    vouchers = await service.day_book(
        organization_id=membership.organization_id, date_from=date_from, date_to=date_to
    )
    return [VoucherSummaryOut.model_validate(v) for v in vouchers]


@router.get("/reports/outstanding")
async def outstanding(
    kind: str = Query(default="receivable", pattern="^(receivable|payable)$"),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AccountingService(session)
    return await service.outstanding(organization_id=membership.organization_id, kind=kind)


@router.get("/reports/{report_type}/export")
async def export_report(
    report_type: str,
    as_on: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    service = AccountingService(session)
    await service.ensure_chart_of_accounts(membership.organization_id)
    await session.commit()

    if report_type == "trial-balance":
        payload = await service.trial_balance(
            organization_id=membership.organization_id, as_on=as_on
        )
    elif report_type == "profit-loss":
        payload = await service.profit_and_loss(
            organization_id=membership.organization_id, date_from=date_from, date_to=date_to
        )
    elif report_type == "balance-sheet":
        payload = await service.balance_sheet(
            organization_id=membership.organization_id, as_on=as_on
        )
    else:
        raise NotFoundError("Unknown report type.")

    csv_text = service.report_to_csv(report_type, payload)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{report_type}.csv"'},
    )
