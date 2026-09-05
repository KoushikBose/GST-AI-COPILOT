"""Import all ORM models so SQLAlchemy's mapper registry (and Alembic
autogenerate) can see them. New model modules must be imported here.
"""

from app.models.accounting import (
    AccountNature,
    BalanceSide,
    Ledger,
    LedgerGroup,
    Voucher,
    VoucherEntry,
    VoucherType,
)
from app.models.agent_run import AgentEvent, AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalRisk, ApprovalStatus, ApprovalType
from app.models.audit import AuditLog
from app.models.chat import ChatChannel, ChatMessage, ChatSession, MessageRole
from app.models.compliance import ComplianceCheck, ComplianceIssue, ComplianceSeverity
from app.models.document import Document, DocumentChunk, DocumentType, DocumentVersion
from app.models.gst_return import GSTReturn, ReturnStatus, ReturnType
from app.models.gst_transaction import GSTTransaction, ITCRecord, ITCStatus, TaxCalculation
from app.models.invoice import (
    Invoice,
    InvoiceDirection,
    InvoiceItem,
    InvoiceStatus,
    InvoiceTax,
    TransactionScope,
)
from app.models.notification import Notification, SystemSetting
from app.models.organization import GSTProfile, Organization
from app.models.party import Customer, Vendor
from app.models.rbac import OrganizationMember, OrgRole
from app.models.reconciliation import (
    Gstr2bRecord,
    ReconciliationMatch,
    ReconciliationMatchStatus,
    ReconciliationRun,
    ReconciliationSource,
)
from app.models.user import User

__all__ = [
    "AccountNature",
    "AgentEvent",
    "AgentRun",
    "AgentRunStatus",
    "BalanceSide",
    "Approval",
    "ApprovalRisk",
    "ApprovalStatus",
    "ApprovalType",
    "AuditLog",
    "ChatChannel",
    "ChatMessage",
    "ChatSession",
    "ComplianceCheck",
    "ComplianceIssue",
    "ComplianceSeverity",
    "Customer",
    "Document",
    "DocumentChunk",
    "DocumentType",
    "DocumentVersion",
    "GSTProfile",
    "GSTReturn",
    "GSTTransaction",
    "Gstr2bRecord",
    "ITCRecord",
    "ITCStatus",
    "Invoice",
    "InvoiceDirection",
    "InvoiceItem",
    "InvoiceStatus",
    "InvoiceTax",
    "Ledger",
    "LedgerGroup",
    "MessageRole",
    "Notification",
    "Organization",
    "OrganizationMember",
    "OrgRole",
    "ReconciliationMatch",
    "ReconciliationMatchStatus",
    "ReconciliationRun",
    "ReconciliationSource",
    "ReturnStatus",
    "ReturnType",
    "SystemSetting",
    "TaxCalculation",
    "TransactionScope",
    "User",
    "Vendor",
    "Voucher",
    "VoucherEntry",
    "VoucherType",
]
