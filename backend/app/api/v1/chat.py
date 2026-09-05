"""Chat endpoints — the web channel's entrypoint into the LangGraph
supervisor via `ConversationService` (see app/services/chat_service.py).
"""

from __future__ import annotations

import uuid

import orjson
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse, ChatSessionOut, ChatSessionSummaryOut
from app.security.dependencies import CurrentMembership, get_current_membership
from app.services.chat_service import ConversationService

router = APIRouter()
logger = get_logger(__name__)


@router.post("", response_model=ChatResponse)
async def send_chat_message(
    body: ChatRequest,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    service = ConversationService(session)
    chat_session, assistant_message, _agent_run = await service.send_message(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        message=body.message,
        session_id=body.session_id,
        channel=body.channel,
    )
    return ChatResponse(
        session_id=chat_session.id,
        message_id=assistant_message.id,
        answer=assistant_message.content,
        intent=assistant_message.intent or "SUPPORT",
        citations=assistant_message.citations or [],
        confidence=float(assistant_message.confidence or 0),
        requires_human_review=assistant_message.requires_human_review,
        calculations=(assistant_message.metadata_json or {}).get("calculations"),
    )


@router.post("/stream")
async def stream_chat_message(
    body: ChatRequest,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """Server-sent-events variant of ``POST /chat``.

    Each event is ``data: <json>\\n\\n`` where the JSON's ``type`` is one of
    ``session`` | ``intent`` | ``delta`` | ``done`` | ``error``.
    """
    service = ConversationService(session)

    async def event_stream():
        try:
            async for event in service.stream_message(
                organization_id=membership.organization_id,
                user_id=membership.user_id,
                message=body.message,
                session_id=body.session_id,
                channel=body.channel,
            ):
                yield f"data: {orjson.dumps(event).decode()}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface as a stream event, never a 500 mid-stream
            payload = {"type": "error", "message": "The assistant stream failed unexpectedly."}
            logger.warning("chat_stream_endpoint_failed", error=str(exc))
            yield f"data: {orjson.dumps(payload).decode()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions", response_model=list[ChatSessionSummaryOut])
async def list_chat_sessions(
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> list[ChatSessionSummaryOut]:
    service = ConversationService(session)
    sessions = await service.list_sessions(
        organization_id=membership.organization_id, user_id=membership.user_id
    )
    return [ChatSessionSummaryOut.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(
    session_id: uuid.UUID,
    membership: CurrentMembership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionOut:
    service = ConversationService(session)
    chat_session = await service.get_session(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        session_id=session_id,
    )
    return ChatSessionOut.model_validate(chat_session)
