"""Human-in-the-loop approval queue service.

Every AI output that is high-impact or low-confidence (invoice extraction,
compliance exception, ITC assessment, return preparation) can be routed
here as an `Approval` (`review_tasks` table). A decision is never silent:
the acting user, their notes and any edited payload are recorded for audit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.approval import Approval, ApprovalRisk, ApprovalStatus, ApprovalType
from app.models.audit import AuditLog
from app.models.gst_return import GSTReturn, ReturnStatus

logger = get_logger(__name__)

_DECISION_STATUS = {
    "approve": ApprovalStatus.APPROVED,
    "reject": ApprovalStatus.REJECTED,
    "modify": ApprovalStatus.MODIFIED,
}


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        approval_type: ApprovalType,
        risk: ApprovalRisk,
        entity_type: str,
        entity_id: str,
        ai_recommendation: dict,
        evidence: list | None = None,
        confidence: float | None = None,
        assigned_to: uuid.UUID | None = None,
    ) -> Approval:
        approval = Approval(
            organization_id=organization_id,
            approval_type=approval_type,
            risk=risk,
            status=ApprovalStatus.PENDING,
            entity_type=entity_type,
            entity_id=entity_id,
            ai_recommendation=ai_recommendation,
            evidence=evidence or [],
            confidence=confidence,
            assigned_to=assigned_to,
        )
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def get(self, *, organization_id: uuid.UUID, approval_id: uuid.UUID) -> Approval:
        result = await self.session.execute(
            select(Approval).where(
                Approval.id == approval_id, Approval.organization_id == organization_id
            )
        )
        approval = result.scalar_one_or_none()
        if approval is None:
            raise NotFoundError("Review task not found.")
        return approval

    async def list_tasks(
        self,
        *,
        organization_id: uuid.UUID,
        status: ApprovalStatus | None = None,
        limit: int = 100,
    ) -> list[Approval]:
        stmt = select(Approval).where(Approval.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Approval.status == status)
        stmt = stmt.order_by(Approval.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def counts_by_status(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(Approval.status, func.count())
            .where(Approval.organization_id == organization_id)
            .group_by(Approval.status)
        )
        return {status.value: count for status, count in result.all()}

    async def decide(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        approval_id: uuid.UUID,
        decision: str,
        notes: str | None = None,
        final_payload: dict | None = None,
    ) -> Approval:
        if decision not in _DECISION_STATUS:
            raise ValidationFailedError(
                f"decision must be one of {sorted(_DECISION_STATUS)}, got {decision!r}."
            )
        approval = await self.get(organization_id=organization_id, approval_id=approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValidationFailedError(
                f"This review task was already {approval.status.value}."
            )
        if decision == "modify" and not final_payload:
            raise ValidationFailedError(
                "A 'modify' decision requires the corrected final_payload."
            )

        approval.status = _DECISION_STATUS[decision]
        approval.decided_by = user_id
        approval.decision_notes = notes
        approval.final_payload = final_payload
        approval.updated_at = datetime.now(UTC)

        await self._propagate_return_decision(approval, decision, notes, user_id)

        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=user_id,
                action=f"approval.{decision}",
                entity_type=approval.entity_type,
                entity_id=approval.entity_id,
                metadata_json={"approval_id": str(approval.id), "notes": notes or ""},
            )
        )
        await self.session.flush()
        logger.info(
            "approval_decided",
            approval_id=str(approval.id),
            decision=decision,
            approval_type=approval.approval_type.value,
        )
        return approval

    async def _propagate_return_decision(
        self, approval: Approval, decision: str, notes: str | None, user_id: uuid.UUID
    ) -> None:
        """When a RETURN_PREPARATION task is decided, move the linked return."""
        if approval.approval_type != ApprovalType.RETURN_PREPARATION:
            return
        try:
            return_id = uuid.UUID(approval.entity_id)
        except ValueError:
            return
        result = await self.session.execute(
            select(GSTReturn).where(
                GSTReturn.id == return_id,
                GSTReturn.organization_id == approval.organization_id,
            )
        )
        gst_return = result.scalar_one_or_none()
        if gst_return is None:
            return
        if decision == "approve":
            gst_return.status = ReturnStatus.APPROVED
            gst_return.approved_by = user_id
        elif decision == "reject":
            gst_return.status = ReturnStatus.GENERATED
        gst_return.review_notes = notes
