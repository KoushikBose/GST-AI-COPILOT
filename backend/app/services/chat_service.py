"""Conversation service: the channel-agnostic layer between a channel
adapter (web /chat endpoint today; WhatsApp/email/voice adapters later —
see module docstring in app/channels/) and the LangGraph supervisor.

    Channel Adapter -> ConversationService -> LangGraph Supervisor -> Agents/Tools

Responsible for: loading/creating the chat session, building conversation
history, invoking the graph, and durably persisting both turns plus an
`AgentRun` audit record. The graph itself never touches the database.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.agents.graph import get_compiled_supervisor_graph
from app.agents.intents import Intent, classify_intent
from app.agents.nodes.gst_calculation import gst_calculation_node
from app.agents.nodes.support import support_node
from app.agents.state import GSTAgentState
from app.config import get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.chat import ChatChannel, ChatMessage, ChatSession, MessageRole
from app.rag.embeddings import get_embedding_provider
from app.rag.pipeline import stream_gst_answer

logger = get_logger(__name__)

_HISTORY_MESSAGES = 20
_RESEARCH_INTENTS = {Intent.GST_QUERY.value, Intent.DOCUMENT_SEARCH.value}
_STREAM_CHUNK = 24  # characters per synthetic delta for non-streamed node output


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_session(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        channel: ChatChannel,
    ) -> ChatSession:
        if session_id is not None:
            stmt = (
                select(ChatSession)
                .where(
                    ChatSession.id == session_id,
                    ChatSession.organization_id == organization_id,
                    ChatSession.user_id == user_id,
                )
                .options(selectinload(ChatSession.messages))
            )
            result = await self.session.execute(stmt)
            chat_session = result.scalar_one_or_none()
            if chat_session is None:
                raise NotFoundError("Chat session not found.")
            return chat_session

        chat_session = ChatSession(
            organization_id=organization_id,
            user_id=user_id,
            channel=channel,
            langgraph_thread_id=str(uuid.uuid4()),
        )
        self.session.add(chat_session)
        await self.session.flush()
        # A freshly created session has no messages. Seed the collection as an
        # empty, already-loaded list so downstream history-building can iterate
        # it without triggering a lazy load — attribute access on an
        # AsyncSession-managed object cannot drive IO outside a greenlet
        # context and would raise MissingGreenlet.
        set_committed_value(chat_session, "messages", [])
        return chat_session

    async def send_message(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        message: str,
        session_id: uuid.UUID | None,
        channel: ChatChannel = ChatChannel.WEB,
    ) -> tuple[ChatSession, ChatMessage, AgentRun]:
        chat_session = await self._get_or_create_session(
            organization_id=organization_id,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
        )
        if chat_session.title is None:
            chat_session.title = message[:80]

        user_message = ChatMessage(
            session_id=chat_session.id, role=MessageRole.USER, content=message
        )
        self.session.add(user_message)
        await self.session.flush()

        history = [
            f"{m.role.value.capitalize()}: {m.content}"
            for m in chat_session.messages[-_HISTORY_MESSAGES:]
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]
        # Adding a child message does not mark the parent session dirty, so
        # update its timestamp explicitly to keep the session list correctly
        # ordered by recent activity.
        chat_session.updated_at = datetime.now(UTC)

        agent_run = AgentRun(
            organization_id=organization_id,
            conversation_id=chat_session.id,
            user_id=user_id,
            status=AgentRunStatus.RUNNING,
        )
        self.session.add(agent_run)
        await self.session.flush()

        graph = get_compiled_supervisor_graph()
        initial_state: GSTAgentState = {
            "tenant_id": str(organization_id),
            "user_id": str(user_id),
            "conversation_id": str(chat_session.id),
            "user_query": message,
            "conversation_history": history,
        }
        config = {"configurable": {"thread_id": chat_session.langgraph_thread_id}}

        start = time.perf_counter()
        try:
            final_state: GSTAgentState = await asyncio.wait_for(
                graph.ainvoke(initial_state, config=config),
                timeout=get_settings().chat_request_timeout_seconds,
            )
            agent_run.status = (
                AgentRunStatus.ESCALATED
                if final_state.get("requires_human_review")
                else AgentRunStatus.COMPLETED
            )
        except TimeoutError:
            logger.warning("agent_run_timed_out", run_id=str(agent_run.id))
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = "The assistant exceeded the request time limit."
            final_state = {
                "answer": (
                    "The assistant could not reach its GST research services in time. "
                    "Please verify that Ollama and Qdrant are running, then try again."
                ),
                "intent": "SUPPORT",
                "citations": [],
                "confidence": 0.0,
                "requires_human_review": True,
            }
        except Exception as exc:
            logger.error("agent_run_failed", error=str(exc), run_id=str(agent_run.id))
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = str(exc)
            await self.session.flush()
            final_state = {
                "answer": (
                    "Something went wrong while processing that request. "
                    "Please try again in a moment."
                ),
                "intent": "SUPPORT",
                "citations": [],
                "confidence": 0.0,
                "requires_human_review": True,
            }

        agent_run.total_latency_ms = int((time.perf_counter() - start) * 1000)
        agent_run.intent = final_state.get("intent")
        agent_run.confidence = final_state.get("confidence")
        agent_run.requires_human_review = final_state.get("requires_human_review", False)

        assistant_message = ChatMessage(
            session_id=chat_session.id,
            role=MessageRole.ASSISTANT,
            content=final_state.get("answer", ""),
            intent=final_state.get("intent"),
            citations=final_state.get("citations", []),
            confidence=final_state.get("confidence"),
            requires_human_review=final_state.get("requires_human_review", False),
            metadata_json={"calculations": final_state.get("calculations")}
            if final_state.get("calculations")
            else {},
        )
        self.session.add(assistant_message)
        await self.session.commit()
        await self.session.refresh(assistant_message)

        return chat_session, assistant_message, agent_run

    async def stream_message(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        message: str,
        session_id: uuid.UUID | None,
        channel: ChatChannel = ChatChannel.WEB,
    ) -> AsyncIterator[dict]:
        """Server-sent-event generator for a chat turn.

        Emits ``{"type": "session", ...}`` first, then ``{"type": "delta",
        ...}`` events as the answer is produced, then a terminal
        ``{"type": "done", ...}`` with citations/confidence/intent. The
        assistant turn and the `AgentRun` audit row are persisted before the
        ``done`` event is emitted, exactly as the non-streaming path does.
        """
        chat_session = await self._get_or_create_session(
            organization_id=organization_id,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
        )
        if chat_session.title is None:
            chat_session.title = message[:80]

        user_message = ChatMessage(
            session_id=chat_session.id, role=MessageRole.USER, content=message
        )
        self.session.add(user_message)
        await self.session.flush()

        history = [
            f"{m.role.value.capitalize()}: {m.content}"
            for m in chat_session.messages[-_HISTORY_MESSAGES:]
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]
        chat_session.updated_at = datetime.now(UTC)

        agent_run = AgentRun(
            organization_id=organization_id,
            conversation_id=chat_session.id,
            user_id=user_id,
            status=AgentRunStatus.RUNNING,
        )
        self.session.add(agent_run)
        await self.session.flush()

        yield {"type": "session", "session_id": str(chat_session.id)}

        llm = get_llm_provider()
        intent = (await classify_intent(llm, message)).value
        yield {"type": "intent", "intent": intent}

        start = time.perf_counter()
        answer_parts: list[str] = []
        citations: list[dict] = []
        confidence = 0.0
        requires_review = False
        calculations: dict | None = None
        error: str | None = None

        try:
            if intent in _RESEARCH_INTENTS:
                async for event in stream_gst_answer(
                    llm=llm,
                    embedding_provider=get_embedding_provider(),
                    question=message,
                    tenant_id=str(organization_id),
                    conversation_history=history,
                ):
                    if event["type"] == "delta":
                        answer_parts.append(event["text"])
                        yield {"type": "delta", "text": event["text"]}
                    elif event["type"] == "final":
                        answer_parts = [event["answer"]]
                        citations = event["citations"]
                        confidence = event["confidence"]
                        requires_review = event["requires_human_review"]
            else:
                node = (
                    gst_calculation_node
                    if intent == Intent.GST_CALCULATION.value
                    else support_node
                )
                state: GSTAgentState = {
                    "tenant_id": str(organization_id),
                    "user_id": str(user_id),
                    "conversation_id": str(chat_session.id),
                    "user_query": message,
                    "conversation_history": history,
                    "intent": intent,
                }
                final_state = await asyncio.wait_for(
                    node(state), timeout=get_settings().chat_request_timeout_seconds
                )
                answer = final_state.get("answer", "")
                confidence = float(final_state.get("confidence", 0) or 0)
                requires_review = bool(final_state.get("requires_human_review", False))
                calculations = final_state.get("calculations")
                for i in range(0, len(answer), _STREAM_CHUNK):
                    chunk = answer[i : i + _STREAM_CHUNK]
                    yield {"type": "delta", "text": chunk}
                answer_parts = [answer]
        except TimeoutError:
            error = "The assistant exceeded the request time limit."
            requires_review = True
        except Exception as exc:  # noqa: BLE001
            logger.error("chat_stream_failed", error=str(exc), run_id=str(agent_run.id))
            error = "Something went wrong while processing that request."
            requires_review = True

        answer_text = "".join(answer_parts).strip() or (
            error or "The assistant could not produce a response."
        )
        if error:
            yield {"type": "delta", "text": f"\n\n{answer_text}"}

        agent_run.total_latency_ms = int((time.perf_counter() - start) * 1000)
        agent_run.intent = intent
        agent_run.confidence = confidence
        agent_run.requires_human_review = requires_review
        agent_run.status = (
            AgentRunStatus.FAILED
            if error
            else AgentRunStatus.ESCALATED
            if requires_review
            else AgentRunStatus.COMPLETED
        )
        if error:
            agent_run.error_message = error

        assistant_message = ChatMessage(
            session_id=chat_session.id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            intent=intent,
            citations=citations,
            confidence=confidence,
            requires_human_review=requires_review,
            metadata_json={"calculations": calculations} if calculations else {},
        )
        self.session.add(assistant_message)
        await self.session.commit()
        await self.session.refresh(assistant_message)

        yield {
            "type": "done",
            "session_id": str(chat_session.id),
            "message_id": str(assistant_message.id),
            "answer": answer_text,
            "intent": intent,
            "citations": citations,
            "confidence": confidence,
            "requires_human_review": requires_review,
            "calculations": calculations,
        }

    async def list_sessions(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.organization_id == organization_id, ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_session(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> ChatSession:
        stmt = (
            select(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.organization_id == organization_id,
                ChatSession.user_id == user_id,
            )
            .options(selectinload(ChatSession.messages))
        )
        result = await self.session.execute(stmt)
        chat_session = result.scalar_one_or_none()
        if chat_session is None:
            raise NotFoundError("Chat session not found.")
        return chat_session
