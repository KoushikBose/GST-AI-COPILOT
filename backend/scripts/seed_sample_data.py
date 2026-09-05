"""Seed the database with realistic SYNTHETIC sample data for local
development: one demo organization, an admin user, customers, vendors, and
100+ invoices with internally-consistent GST arithmetic (computed via the
real `GSTCalculator`, so the demo data behaves exactly like production
would for the deterministic core).

ALL data generated here is synthetic — no real business, GSTIN, or
individual is represented. Every generated GSTIN uses a structurally valid
checksum (via `app.rules.gstin_validator`) so the demo data exercises real
validation logic, but the PAN/entity portions are Faker-random and do not
correspond to any real registration.

Run with:
    make seed
    (or) python -m scripts.seed_sample_data
"""

from __future__ import annotations

import asyncio
import random
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import select

from app.core.database import db_session_context
from app.core.logging import configure_logging, get_logger
from app.models.gst_return import GSTReturn
from app.models.invoice import (
    Invoice,
    InvoiceDirection,
    InvoiceItem,
    InvoiceStatus,
    InvoiceTax,
    TransactionScope,
)
from app.models.organization import GSTProfile, Organization
from app.models.party import Customer, Vendor
from app.models.rbac import OrganizationMember, OrgRole
from app.models.user import User
from app.rules.gst_calculator import GSTCalculator, TransactionType
from app.rules.gstin_validator import _compute_checksum
from app.security.passwords import hash_password

configure_logging()
logger = get_logger(__name__)
fake = Faker("en_IN")

GST_RATES = [Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28")]
HSN_CODES = ["8471", "9983", "998314", "8517", "4820", "3926", "8443"]
STATE_CODES = ["27", "29", "07", "33", "19", "06", "36"]

DEMO_ADMIN_EMAIL = "demo.admin@gst-copilot.example"
DEMO_ADMIN_PASSWORD = "SyntheticDemo#2026"  # dev-only fixture, never used in production


def _synthetic_gstin(state_code: str) -> str:
    pan = fake.bothify(text="?????####?", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ").upper()
    entity_code = "1"
    prefix = f"{state_code}{pan}{entity_code}Z"
    checksum = _compute_checksum(prefix)
    return prefix + checksum


async def _create_organization(session) -> tuple[Organization, User]:
    org = Organization(
        name="Synthetic Demo Traders Pvt Ltd",
        legal_name="Synthetic Demo Traders Private Limited",
        slug="synthetic-demo-traders",
        is_active=True,
    )
    session.add(org)
    await session.flush()

    session.add(
        GSTProfile(
            organization_id=org.id,
            gstin=_synthetic_gstin("27"),
            legal_name=org.legal_name,
            trade_name="Demo Traders",
            state_code="27",
            registration_type="regular",
            is_verified=True,
        )
    )

    admin = User(
        email=DEMO_ADMIN_EMAIL,
        hashed_password=hash_password(DEMO_ADMIN_PASSWORD),
        full_name="Synthetic Demo Admin",
        is_active=True,
        is_email_verified=True,
    )
    session.add(admin)
    await session.flush()

    session.add(
        OrganizationMember(
            organization_id=org.id, user_id=admin.id, role=OrgRole.ORG_ADMIN, is_active=True
        )
    )
    await session.flush()
    return org, admin


async def _create_parties(session, org: Organization) -> tuple[list[Customer], list[Vendor]]:
    customers = []
    for _ in range(10):
        state = random.choice(STATE_CODES)
        customer = Customer(
            organization_id=org.id,
            name=f"Synthetic {fake.company()}",
            gstin=_synthetic_gstin(state),
            state_code=state,
            email=fake.company_email(),
            phone=fake.phone_number(),
            address=fake.address(),
        )
        session.add(customer)
        customers.append(customer)

    vendors = []
    for _ in range(10):
        state = random.choice(STATE_CODES)
        vendor = Vendor(
            organization_id=org.id,
            name=f"Synthetic {fake.company()}",
            gstin=_synthetic_gstin(state),
            state_code=state,
            email=fake.company_email(),
            phone=fake.phone_number(),
            address=fake.address(),
        )
        session.add(vendor)
        vendors.append(vendor)

    await session.flush()
    return customers, vendors


def _build_invoice(
    *,
    org: Organization,
    direction: InvoiceDirection,
    counterparty_name: str,
    counterparty_gstin: str,
    own_gstin: str,
    index: int,
    inject_issue: bool,
) -> Invoice:
    calculator = GSTCalculator()
    scope = random.choice(list(TransactionScope))
    txn_type = TransactionType(scope.value)

    invoice_date = date.today() - timedelta(days=random.randint(0, 180))
    invoice = Invoice(
        organization_id=org.id,
        direction=direction,
        status=InvoiceStatus.EXTRACTED,
        invoice_number=f"SYN-{invoice_date.year}-{index:05d}",
        invoice_date=invoice_date.isoformat(),
        supplier_name=counterparty_name if direction == InvoiceDirection.PURCHASE else org.name,
        supplier_gstin=(
            counterparty_gstin if direction == InvoiceDirection.PURCHASE else own_gstin
        ),
        buyer_name=org.name if direction == InvoiceDirection.PURCHASE else counterparty_name,
        buyer_gstin=(own_gstin if direction == InvoiceDirection.PURCHASE else counterparty_gstin),
        place_of_supply=fake.state(),
        currency="INR",
        transaction_scope=scope,
        extracted_fields={},
        ocr_confidence=Decimal(str(round(random.uniform(0.85, 0.99), 3))),
    )

    # Deliberately break ~15% of invoices so the compliance/ITC demo has
    # something to find (missing GSTIN is the easiest, clearest example).
    if inject_issue:
        invoice.supplier_gstin = None

    num_items = random.randint(1, 4)
    taxable_total = Decimal("0")
    cgst_total = sgst_total = igst_total = cess_total = Decimal("0")

    for line_no in range(1, num_items + 1):
        taxable_value = Decimal(random.randint(500, 50000))
        rate = random.choice(GST_RATES)
        calc = calculator.calculate(
            taxable_value=taxable_value, gst_rate=rate, transaction_type=txn_type
        )
        invoice.items.append(
            InvoiceItem(
                line_number=line_no,
                description=fake.bs().title(),
                hsn_sac=random.choice(HSN_CODES),
                quantity=Decimal(random.randint(1, 20)),
                unit="NOS",
                unit_price=(taxable_value / Decimal(random.randint(1, 20))).quantize(
                    Decimal("0.01")
                ),
                taxable_value=calc.taxable_value,
                gst_rate=rate,
                cess_rate=Decimal("0"),
                cgst=calc.cgst,
                sgst=calc.sgst,
                igst=calc.igst,
                cess=calc.cess,
                line_total=calc.grand_total,
            )
        )
        taxable_total += calc.taxable_value
        cgst_total += calc.cgst
        sgst_total += calc.sgst
        igst_total += calc.igst
        cess_total += calc.cess

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

    return invoice


async def _run_compliance_and_returns(session, org: Organization, admin: User) -> None:
    """Populate compliance checks + a couple of return drafts so the
    compliance, approvals, analytics and returns pages have data on a fresh
    seed (not just the invoice list)."""
    from app.models.gst_return import ReturnType
    from app.services.approval_service import ApprovalService
    from app.services.compliance_service import ComplianceService
    from app.services.return_service import ReturnService

    await session.flush()
    result = await session.execute(
        select(Invoice).where(Invoice.organization_id == org.id)
    )
    invoices = list(result.scalars().all())

    compliance = ComplianceService(session)
    approvals = ApprovalService(session)
    from app.models.approval import ApprovalRisk, ApprovalType
    from app.models.compliance import ComplianceSeverity

    for invoice in invoices:
        await session.refresh(invoice, attribute_names=["items"])
        check = await compliance.run_check(invoice)
        if any(i.severity == ComplianceSeverity.CRITICAL for i in check.issues):
            await approvals.create(
                organization_id=org.id,
                approval_type=ApprovalType.COMPLIANCE_EXCEPTION,
                risk=ApprovalRisk.HIGH,
                entity_type="invoice",
                entity_id=str(invoice.id),
                ai_recommendation={
                    "compliance_score": check.score,
                    "issues": [
                        {"rule_code": i.rule_code, "severity": i.severity.value}
                        for i in check.issues
                    ],
                },
            )

    # Post every extracted invoice to the double-entry books so the Trial
    # Balance / P&L / Balance Sheet and Day Book have real data on a fresh seed.
    from app.services.accounting_service import AccountingService

    accounting = AccountingService(session)
    await accounting.ensure_chart_of_accounts(org.id)
    posted = 0
    for invoice in invoices:
        try:
            await accounting.post_invoice(
                organization_id=org.id, user_id=admin.id, invoice=invoice
            )
            posted += 1
        except Exception:  # noqa: BLE001 - skip anything that can't be posted cleanly
            continue
    logger.info("seed_books_posted", vouchers=posted)

    periods = sorted({inv.invoice_date[:7] for inv in invoices if inv.invoice_date})[-2:]
    returns_service = ReturnService(session)
    for period in periods:
        for return_type in (ReturnType.GSTR1, ReturnType.GSTR3B):
            await returns_service.generate(
                organization_id=org.id,
                user_id=admin.id,
                return_type=return_type,
                period=period,
            )
    if periods:
        oldest = periods[0]
        result = await session.execute(
            select(GSTReturn).where(
                GSTReturn.organization_id == org.id,
                GSTReturn.period == oldest,
                GSTReturn.return_type == ReturnType.GSTR1,
            )
        )
        gst_return = result.scalar_one_or_none()
        if gst_return is not None:
            await returns_service.submit_for_review(
                organization_id=org.id, user_id=admin.id, return_id=gst_return.id
            )
    logger.info("seed_compliance_and_returns_done", checks=len(invoices), periods=periods)


async def seed(invoice_count: int = 120) -> None:
    async with db_session_context() as session:
        org, admin = await _create_organization(session)
        gst_profile_result = await session.execute(
            select(GSTProfile).where(GSTProfile.organization_id == org.id)
        )
        gst_profile = gst_profile_result.scalar_one_or_none()
        own_gstin = gst_profile.gstin if gst_profile else _synthetic_gstin("27")

        customers, vendors = await _create_parties(session, org)

        for i in range(1, invoice_count + 1):
            direction = InvoiceDirection.SALES if i % 2 == 0 else InvoiceDirection.PURCHASE
            counterparty = random.choice(
                customers if direction == InvoiceDirection.SALES else vendors
            )
            invoice = _build_invoice(
                org=org,
                direction=direction,
                counterparty_name=counterparty.name,
                counterparty_gstin=counterparty.gstin or _synthetic_gstin("27"),
                own_gstin=own_gstin,
                index=i,
                inject_issue=(i % 7 == 0),
            )
            session.add(invoice)

        await _run_compliance_and_returns(session, org, admin)

        logger.info(
            "seed_complete",
            organization=org.name,
            admin_email=DEMO_ADMIN_EMAIL,
            invoice_count=invoice_count,
        )

    print("Synthetic demo data seeded.")
    print("  Organization: Synthetic Demo Traders Pvt Ltd")
    print(f"  Admin login:  {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
    print(f"  Invoices:     {invoice_count} (synthetic, ~1/7 intentionally non-compliant)")


if __name__ == "__main__":
    asyncio.run(seed())
