from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

from app.agents.chat import ChatAssistantAgent
from app.agents.chat.complexity import AGENTIC_TASK, ChatComplexityClassifier
from app.agents.chat.context_budget import ChatContextBudget, context_compression_metadata, maybe_compress_context
from app.agents.chat.tools import ChatToolExecutor, city_from_message, keyword_from_message
from app.agents.runtime import AgentContext, AgentLifecycleRecorder, AgentRunner
from app.agents.supervisor import SupervisorAgent, SupervisorTurn
from app.core.providers.claude_provider import ClaudeProviderError
from app.core.providers.factory import get_provider
from app.core.settings import settings
from app.repositories.assistant_memory_repository import AssistantMemoryRepository
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.prompts import PromptRegistry
from app.services.ai_assistant_file_memory import AIMemoryFileService
from app.services.assistant_memory_command_service import AssistantMemoryCommandService
from app.services.assistant_memory_markdown_service import AssistantMemoryMarkdownService
from app.services.chat_output_format import format_assistant_plain_text
from app.services.citation_protocol import build_citation_protocol, normalize_knowledge_citations
from app.services.scheduled_task_service import ScheduledTaskChatResult, ScheduledTaskService
from app.services.streaming import chunk_text, encode_sse_event, stream_event
from app.services.trace import (
    build_chat_evidence_summary,
    build_eval_tags,
    build_retrieval_summary,
    build_safety_boundary,
    new_agent_run_id,
    new_request_id,
)

AI_ASSISTANT_TYPE = "ai_assistant"


@dataclass
class ChatServiceError(Exception):
    status_code: int
    code: int
    message: str


class ChatService:
    def __init__(self, chat_repository: ChatSessionRepository, supervisor: SupervisorAgent | None = None):
        self.chat_repository = chat_repository
        self.supervisor = supervisor or SupervisorAgent()

    # 一次用户消息从这里进入 AI 助手主链路：建上下文、判复杂度、选工具、调模型、写会话。
    async def stream_events(
        self,
        *,
        user_id: str,
        message: str | None,
        session_id: str | None = None,
        action: str = "send",
        skip_scheduled_task_detection: bool = False,
        channel: str = "web",
        telegram_chat_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        started_at = time.perf_counter()
        request_id = new_request_id()
        agent_run_id = new_agent_run_id("chat")
        lifecycle = AgentLifecycleRecorder(
            assistant_type=AI_ASSISTANT_TYPE,
            request_id=request_id,
            agent_run_id=agent_run_id,
        )
        provider = get_provider()
        assistant_agent = ChatAssistantAgent()
        session = self._load_or_create_session(user_id=user_id, session_id=session_id)
        effective_message = self._message_for_action(session=session, message=message, action=action)
        history = list(session.messages or [])
        conversation_id = str(session.id)
        if action == "send":
            memory_command = AssistantMemoryCommandService().handle(user_id=user_id, message=effective_message)
            if memory_command is not None:
                async for event in self._stream_memory_command_result(
                    conversation_id=conversation_id,
                    request_id=request_id,
                    agent_run_id=agent_run_id,
                    provider=provider,
                    action=action,
                    result=memory_command,
                    started_at=started_at,
                ):
                    yield event
                return
        # 定时任务会改变任务表和收件箱状态，所以必须在普通模型生成前拦截。
        if action == "send" and not skip_scheduled_task_detection:
            scheduled_result = ScheduledTaskService(repository=ScheduledTaskRepository(self.chat_repository.db)).handle_chat_message(
                user_id=user_id,
                message=effective_message,
                session_id=conversation_id,
                channel=channel,
                telegram_chat_id=telegram_chat_id,
            )
            if scheduled_result.handled:
                async for event in self._stream_scheduled_task_result(
                    session=session,
                    provider=provider,
                    request_id=request_id,
                    agent_run_id=agent_run_id,
                    user_message=effective_message,
                    result=scheduled_result,
                    started_at=started_at,
                ):
                    yield event
                return
        # 轻量问题直接回答；求职任务、技术问题、岗位搜索等进入 Supervisor + 工具链路。
        complexity = ChatComplexityClassifier().classify(effective_message)
        file_memory_service = AIMemoryFileService()
        file_memory_context = file_memory_service.read_context(user_id=user_id, session_id=conversation_id)
        memory_context = file_memory_service.public_context_metadata(file_memory_context)
        base_turn = (
            self._simple_turn(message=effective_message, history=history, file_memory_context=file_memory_context)
            if complexity != AGENTIC_TASK
            else self.supervisor.plan_turn(message=effective_message, history=history, tool_context={})
        )
        lifecycle.complete(
            "BeforeTurn",
            session_id=conversation_id,
            action=action,
            history_count=len(history),
            memory_count=memory_context.get("count", 0),
        )
        lifecycle.complete("BeforeReasoning", intent=base_turn.intent, tools=base_turn.tools)
        user_message_id = f"user-{uuid4()}"
        assistant_message_id = self._assistant_message_id_for_action(session=session, action=action)
        previous_assistant_content = self._last_message(session=session, role="assistant").get("content", "") if action == "continue" else ""

        yield stream_event(
            "start",
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            metadata={
                "action": action,
                "model": provider.model,
                "provider": provider.name,
                "source": provider.name,
                "intent": base_turn.intent,
                "status": "running",
                "interrupted": False,
                "assistant_type": AI_ASSISTANT_TYPE,
                "agent_name": assistant_agent.agent_name,
                "agent_chain": [self.supervisor.agent_name, assistant_agent.agent_name],
                "request_id": request_id,
                "agent_run_id": agent_run_id,
                "eval_tags": build_eval_tags(assistant_type=AI_ASSISTANT_TYPE, intent=base_turn.intent, tools=base_turn.tools),
                "safety_boundary": build_safety_boundary(assistant_type=AI_ASSISTANT_TYPE, tools=base_turn.tools),
                "memory_scope": self._memory_scope(),
                "memory_used": memory_context,
                "complexity": complexity,
                "prompt_template_id": base_turn.prompt_template_id,
                "prompt_template_version": base_turn.prompt_template_version,
                "memory_files_used": memory_context.get("memory_files", []),
                "agent_pipeline": lifecycle.summary(),
            },
        )

        tool_context = (
            self._run_tools(user_id=user_id, intent=base_turn.intent, message=effective_message, tools=base_turn.tools)
            if complexity == AGENTIC_TASK
            else {}
        )
        tool_context["assistant_memory"] = memory_context
        tool_context["assistant_file_memory"] = {"content": file_memory_context.get("summary_text", "")}
        if complexity == AGENTIC_TASK and (memory_snapshot_content := self._load_assistant_memory_snapshot_content(user_id=user_id)):
            tool_context["assistant_memory_snapshot"] = {"content": memory_snapshot_content}

        compression = maybe_compress_context(
            history=history,
            file_memory_context=file_memory_context,
            tool_context=tool_context,
            prompt=base_turn.prompt,
            budget=ChatContextBudget(
                context_window_tokens=settings.llm_context_window_tokens,
                compression_ratio=settings.llm_context_compression_ratio,
                reserved_output_tokens=settings.llm_context_reserved_output_tokens,
            ),
        )
        context_compression = context_compression_metadata(compression)
        if compression.get("triggered"):
            history = compression["history"]
            file_memory_context = compression["file_memory_context"]
            tool_context["assistant_file_memory"] = {"content": file_memory_context.get("summary_text", "")}

        turn = (
            self.supervisor.plan_turn(message=effective_message, history=history, tool_context=tool_context)
            if complexity == AGENTIC_TASK
            else self._simple_turn(message=effective_message, history=history, file_memory_context=file_memory_context)
        )
        lifecycle.complete(
            "PromptRender",
            prompt_chars=len(turn.prompt),
            system_prompt_chars=len(turn.system_prompt),
            tool_count=len([name for name in turn.tools if tool_context.get(name)]),
            context_compression=context_compression,
        )
        lifecycle.complete("Reasoner", provider=provider.name, model=provider.model, runtime="custom")
        status = "ready"
        source = provider.name
        issues: list[str] = []
        raw_parts: list[str] = []
        emitted_text = ""
        first_token_latency_ms: int | None = None
        delta_count = 0

        runtime_metadata_patch: dict[str, Any] = {"agent_runtime": "custom", "context_compression": context_compression}

        try:
            agent_context = AgentContext(provider=provider, request_id=request_id, assistant_type=AI_ASSISTANT_TYPE)
            async for content_delta in AgentRunner().stream(
                assistant_agent,
                prompt=turn.prompt,
                context=agent_context,
                system_prompt=turn.system_prompt,
                temperature=0.2,
                max_tokens=700,
            ):
                if not content_delta:
                    continue
                raw_parts.append(content_delta)
                plain_so_far = format_assistant_plain_text("".join(raw_parts))
                outgoing_delta = self._plain_stream_delta(clean_so_far=plain_so_far, emitted_text=emitted_text)
                if not outgoing_delta:
                    continue
                if first_token_latency_ms is None:
                    first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)
                delta_count += 1
                emitted_text += outgoing_delta
                yield stream_event(
                    "delta",
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    content_delta=outgoing_delta,
                )
            final_text = format_assistant_plain_text("".join(raw_parts))
            tail_delta = self._plain_stream_delta(clean_so_far=final_text, emitted_text=emitted_text)
            if tail_delta:
                if first_token_latency_ms is None:
                    first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)
                delta_count += 1
                emitted_text += tail_delta
                yield stream_event(
                    "delta",
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    content_delta=tail_delta,
                )
            if not final_text.strip():
                raise ClaudeProviderError("model returned empty content", error_type="empty_response")
        except asyncio.CancelledError:
            partial_text = emitted_text
            self._complete_missing_reasoning_phases(lifecycle=lifecycle, turn=turn, tool_context=tool_context, provider=provider)
            lifecycle.complete("AfterReasoning", status="interrupted", delta_count=delta_count)
            lifecycle.complete("AfterTurn", memory_updates={"confirmed_count": 0, "pending_count": 0})
            metadata = self._stream_metadata(
                provider=provider,
                source=source,
                status="interrupted",
                action=action,
                turn=turn,
                tool_context=tool_context,
                issues=["client aborted stream"],
                first_token_latency_ms=first_token_latency_ms,
                started_at=started_at,
                delta_count=delta_count,
                interrupted=True,
                memory_context=memory_context,
                memory_updates=self._empty_memory_updates(),
                request_id=request_id,
                agent_run_id=agent_run_id,
                agent_pipeline=lifecycle.summary(),
                agent_name=assistant_agent.agent_name,
                agent_chain=[self.supervisor.agent_name, assistant_agent.agent_name],
                complexity=complexity,
                file_memory_context=file_memory_context,
                consolidation_summary={"compacted": False, "reason": "interrupted"},
                dream_update_summary={"updated_files": [], "reason": "interrupted"},
                extra_metadata=runtime_metadata_patch,
            )
            if partial_text.strip():
                self._persist_stream_result(
                    session=session,
                    action=action,
                    user_message=effective_message,
                    assistant_message=partial_text,
                    assistant_full_content=self._combined_continue_content(previous_assistant_content, partial_text) if action == "continue" else partial_text,
                    last_agent=turn.agent_name,
                    agent_states={turn.agent_name: "interrupted", "intent": turn.intent, "tools": turn.tools},
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                    metadata=metadata,
                )
            raise
        except ClaudeProviderError as exc:
            final_text = format_assistant_plain_text(self.supervisor.fallback_text(message=effective_message, tool_context=tool_context, error=exc.message))
            source = "fallback_rule"
            status = "fallback"
            issues.append(exc.message)
            for content_delta in chunk_text(final_text):
                if first_token_latency_ms is None:
                    first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)
                delta_count += 1
                yield stream_event(
                    "delta",
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    content_delta=content_delta,
                )

        validation_status = "passed" if final_text.strip() else "failed"
        lifecycle.complete("AfterReasoning", status=status, delta_count=delta_count, validation_status=validation_status)
        # 回答完成后再写文件记忆，避免中断或空回答污染长期上下文。
        memory_updates = self._remember_turn(
            user_id=user_id,
            session_id=conversation_id,
            intent=turn.intent,
            tools=turn.tools,
            status=status,
            tool_context=tool_context,
            request_id=request_id,
            agent_run_id=agent_run_id,
            user_message=effective_message,
            assistant_message=final_text,
            action=action,
            file_memory_service=file_memory_service,
            force_consolidation=bool(context_compression.get("triggered")),
        )
        lifecycle.complete(
            "AfterTurn",
            memory_updates={
                "pending_count": memory_updates.get("pending_count", 0),
                "confirmed_count": memory_updates.get("confirmed_count", 0),
            },
        )
        metadata = self._stream_metadata(
            provider=provider,
            source=source,
            status=status,
            action=action,
            turn=turn,
            tool_context=tool_context,
            issues=issues,
            first_token_latency_ms=first_token_latency_ms,
            started_at=started_at,
            delta_count=delta_count,
            interrupted=False,
            validation_status=validation_status,
            memory_context=memory_context,
            memory_updates=memory_updates,
            request_id=request_id,
            agent_run_id=agent_run_id,
            agent_pipeline=lifecycle.summary(),
            agent_name=assistant_agent.agent_name,
            agent_chain=[self.supervisor.agent_name, assistant_agent.agent_name],
            complexity=complexity,
            file_memory_context=file_memory_context,
            consolidation_summary=memory_updates.get("consolidation") or {},
            dream_update_summary=memory_updates.get("dream") or {},
            extra_metadata=runtime_metadata_patch,
        )
        assistant_full_content = self._combined_continue_content(previous_assistant_content, final_text) if action == "continue" else final_text
        self._persist_stream_result(
            session=session,
            action=action,
            user_message=effective_message,
            assistant_message=final_text,
            assistant_full_content=assistant_full_content,
            last_agent=turn.agent_name,
            agent_states={turn.agent_name: status, "intent": turn.intent, "tools": turn.tools},
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            metadata=metadata,
        )
        yield stream_event(
            "end",
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            full_content=assistant_full_content,
            metadata=metadata,
        )

    @staticmethod
    def _complete_missing_reasoning_phases(*, lifecycle: AgentLifecycleRecorder, turn, tool_context: dict[str, Any], provider) -> None:
        phases = lifecycle.summary().get("phases") or []
        if "PromptRender" not in phases:
            lifecycle.complete(
                "PromptRender",
                prompt_chars=len(getattr(turn, "prompt", "")),
                system_prompt_chars=len(getattr(turn, "system_prompt", "")),
                tool_count=len([name for name in getattr(turn, "tools", []) if tool_context.get(name)]),
            )
        if "Reasoner" not in lifecycle.summary().get("phases", []):
            lifecycle.complete("Reasoner", provider=provider.name, model=provider.model, runtime="custom")

    async def _stream_memory_command_result(
        self,
        *,
        conversation_id: str,
        request_id: str,
        agent_run_id: str,
        provider,
        action: str,
        result,
        started_at: float,
    ) -> AsyncIterator[dict[str, Any]]:
        message_id = f"assistant-{uuid4()}"
        metadata = {
            "action": action,
            "assistant_type": AI_ASSISTANT_TYPE,
            "request_id": request_id,
            "agent_run_id": agent_run_id,
            "model": provider.model,
            "provider": provider.name,
            "source": "memory_command",
            "status": result.status,
            "intent": "memory_command",
            "tools": [],
            "complexity": "command",
            "agent_runtime": "custom",
            "memory_command": result.command,
            "interrupted": False,
            "delta_count": 0,
            "total_latency_ms": 0,
        }
        yield stream_event(
            "start",
            conversation_id=conversation_id,
            message_id=message_id,
            metadata={**metadata, "status": "running"},
        )
        delta_count = 0
        for delta in chunk_text(result.reply):
            delta_count += 1
            yield stream_event(
                "delta",
                conversation_id=conversation_id,
                message_id=message_id,
                content_delta=delta,
            )
        metadata["delta_count"] = delta_count
        metadata["total_latency_ms"] = int((time.perf_counter() - started_at) * 1000)
        yield stream_event(
            "end",
            conversation_id=conversation_id,
            message_id=message_id,
            full_content=result.reply,
            metadata=metadata,
        )

    def _message_for_action(self, *, session, message: str | None, action: str) -> str:
        if action == "send":
            return (message or "").strip()

        if action == "regenerate":
            last_user = self._last_message(session=session, role="user")
            content = str(last_user.get("content") or "").strip()
            if not content:
                raise ChatServiceError(status_code=400, code=6003, message="No previous user message to regenerate")
            return content

        if action == "continue":
            last_assistant = self._last_message(session=session, role="assistant")
            content = str(last_assistant.get("content") or "").strip()
            if not content:
                raise ChatServiceError(status_code=400, code=6004, message="No previous assistant message to continue")
            return PromptRegistry().render("chat/continue", {"previous_answer": content[-1800:]}).user

        raise ChatServiceError(status_code=400, code=6005, message="Unsupported chat action")

    def _simple_turn(self, *, message: str, history: list[dict], file_memory_context: dict[str, Any]) -> SupervisorTurn:
        rendered = PromptRegistry().render(
            "chat/simple_answer",
            {
                "message": message,
                "history_text": self.supervisor._history_to_text(history),
                "memory_text": str(file_memory_context.get("summary_text") or "")[:1600],
            },
        )
        return SupervisorTurn(
            agent_name=self.supervisor.agent_name,
            intent="simple_answer",
            focus="simple_answer",
            steps=["direct_answer"],
            tools=[],
            system_prompt=rendered.system,
            prompt=rendered.user,
            prompt_template_id=rendered.template_id,
            prompt_template_version=rendered.version,
        )

    async def _stream_scheduled_task_result(
        self,
        *,
        session,
        provider,
        request_id: str,
        agent_run_id: str,
        user_message: str,
        result: ScheduledTaskChatResult,
        started_at: float,
    ) -> AsyncIterator[dict[str, Any]]:
        assistant_message_id = f"assistant-{uuid4()}"
        user_message_id = f"user-{uuid4()}"
        conversation_id = str(session.id)
        # 定时任务回复仍复用 SSE 协议，但不再调用普通模型推理链。
        base_metadata = {
            "action": "send",
            "assistant_type": AI_ASSISTANT_TYPE,
            "request_id": request_id,
            "agent_run_id": agent_run_id,
            "agent_name": "scheduled_task_agent",
            "agent_chain": ["scheduled_task_agent"],
            "agent_pipeline": {"phases": ["BeforeTurn", "ScheduledTaskDetect", "AfterTurn"]},
            "eval_tags": ["ai_assistant", "scheduled_task", str(result.action or "")],
            "model": provider.model,
            "provider": provider.name,
            "source": "scheduled_task",
            "status": "ready",
            "intent": "scheduled_task",
            "tools": [],
            "complexity": "scheduled_task",
            "prompt_template_id": "chat/schedule_extract",
            "prompt_template_version": "v1",
            "validation_status": "passed",
            "issues": [],
            "interrupted": False,
            "source_kind": "scheduled_task",
            "fallback_notice": None,
            "memory_scope": self._memory_scope(),
            "memory_used": self._empty_memory_used(),
            "memory_updates": self._empty_memory_updates(),
            "memory_snapshot": self._empty_memory_snapshot(),
            "retrieval_summary": {},
            "evidence_summary": {"tool_count": 0},
            "safety_boundary": build_safety_boundary(assistant_type=AI_ASSISTANT_TYPE, tools=[]),
            "knowledge_references": {"count": 0, "items": []},
            "citation_protocol": build_citation_protocol(tool_context={}, memory_context=self._empty_memory_used(), memory_updates=self._empty_memory_updates()),
            "recommendations": [],
            "suggested_actions": [
                {
                    "kind": "scheduled_tasks",
                    "label": "查看任务收件箱",
                    "href": "/chat",
                    "description": "在 AI 助手侧栏查看任务、执行结果和暂停/取消入口。",
                }
            ],
            **(result.metadata or {}),
        }
        yield stream_event(
            "start",
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            metadata={**base_metadata, "first_token_latency_ms": None, "delta_count": 0},
        )
        full_text = format_assistant_plain_text(result.reply or "定时任务已处理。")
        delta_count = 0
        first_token_latency_ms: int | None = None
        for content_delta in chunk_text(full_text):
            if first_token_latency_ms is None:
                first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)
            delta_count += 1
            yield stream_event(
                "delta",
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                content_delta=content_delta,
            )
        metadata = {
            **base_metadata,
            "first_token_latency_ms": first_token_latency_ms,
            "total_latency_ms": int((time.perf_counter() - started_at) * 1000),
            "delta_count": delta_count,
        }
        self._persist_stream_result(
            session=session,
            action="send",
            user_message=user_message,
            assistant_message=full_text,
            assistant_full_content=full_text,
            last_agent="scheduled_task_agent",
            agent_states={"scheduled_task_agent": result.action or "handled", "intent": "scheduled_task", "tools": []},
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            metadata=metadata,
        )
        yield stream_event(
            "end",
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            full_content=full_text,
            metadata=metadata,
        )

    def list_sessions(self, *, user_id: str, limit: int = 30) -> dict[str, Any]:
        sessions = self.chat_repository.list_by_user_id(user_id=user_id, limit=limit)
        return {
            "total": len(sessions),
            "sessions": [self._serialize_session_summary(session) for session in sessions],
        }

    def get_session(self, *, user_id: str, session_id: str) -> dict[str, Any]:
        session = self.chat_repository.get_by_id(session_id=session_id, user_id=user_id)
        if session is None:
            raise ChatServiceError(status_code=404, code=6002, message="Chat session not found")
        return {
            "session_id": str(session.id),
            "messages": list(session.messages or []),
            "agent_states": session.agent_states,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    @staticmethod
    def _serialize_session_summary(session) -> dict[str, Any]:
        messages = list(session.messages or [])
        first_user = next((str(item.get("content") or "") for item in messages if item.get("role") == "user"), "")
        last_user = next((str(item.get("content") or "") for item in reversed(messages) if item.get("role") == "user"), "")
        last_message = next((str(item.get("content") or "") for item in reversed(messages) if item.get("content")), "")
        title = first_user[:32] or "新对话"
        assistant_messages = [str(item.get("content") or "") for item in messages if item.get("role") == "assistant"]
        turn_count = len([item for item in messages if item.get("role") == "user"])
        return {
            "session_id": str(session.id),
            "title": title,
            "preview": last_message[:80],
            "summary": (assistant_messages[-1] if assistant_messages else last_message)[:120],
            "last_question": last_user[:120],
            "completion": f"{turn_count} turns",
            "message_count": len(messages),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    def _assistant_message_id_for_action(self, *, session, action: str) -> str:
        if action in {"regenerate", "continue"}:
            last_assistant = self._last_message(session=session, role="assistant")
            if last_assistant.get("id"):
                return str(last_assistant["id"])
        return f"assistant-{uuid4()}"

    @staticmethod
    def _last_message(*, session, role: str) -> dict[str, Any]:
        for item in reversed(list(session.messages or [])):
            if item.get("role") == role:
                return item
        return {}

    @staticmethod
    def _combined_continue_content(previous_content: str, continuation: str) -> str:
        if not previous_content:
            return continuation
        if not continuation:
            return previous_content
        return f"{previous_content.rstrip()}\n\n{continuation.lstrip()}"

    @staticmethod
    def _plain_stream_delta(*, clean_so_far: str, emitted_text: str) -> str:
        if not clean_so_far:
            return ""
        if clean_so_far.startswith(emitted_text):
            return clean_so_far[len(emitted_text) :]
        return ""

    def _persist_stream_result(
        self,
        *,
        session,
        action: str,
        user_message: str,
        assistant_message: str,
        assistant_full_content: str,
        last_agent: str,
        agent_states: dict,
        user_message_id: str,
        assistant_message_id: str,
        metadata: dict,
    ) -> None:
        if action == "send":
            self.chat_repository.append_turn(
                session=session,
                user_message=user_message,
                assistant_message=assistant_message,
                last_agent=last_agent,
                agent_states=agent_states,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                assistant_metadata=metadata,
            )
            return

        if action == "regenerate":
            self.chat_repository.replace_last_assistant(
                session=session,
                assistant_message=assistant_message,
                last_agent=last_agent,
                agent_states=agent_states,
                assistant_message_id=assistant_message_id,
                assistant_metadata=metadata,
            )
            return

        if action == "continue":
            delta_to_append = assistant_full_content
            previous = self._last_message(session=session, role="assistant").get("content", "")
            if isinstance(previous, str) and assistant_full_content.startswith(previous):
                delta_to_append = assistant_full_content[len(previous) :]
            self.chat_repository.append_to_last_assistant(
                session=session,
                assistant_delta=delta_to_append,
                last_agent=last_agent,
                agent_states=agent_states,
                assistant_metadata=metadata,
            )
            return

        raise ChatServiceError(status_code=400, code=6005, message="Unsupported chat action")

    def _stream_metadata(
        self,
        *,
        provider,
        source: str,
        status: str,
        action: str,
        turn,
        tool_context: dict[str, Any],
        issues: list[str],
        first_token_latency_ms: int | None,
        started_at: float,
        delta_count: int,
        interrupted: bool,
        validation_status: str = "failed",
        memory_context: dict[str, Any] | None = None,
        memory_updates: dict[str, Any] | None = None,
        request_id: str | None = None,
        agent_run_id: str | None = None,
        agent_pipeline: dict[str, Any] | None = None,
        agent_name: str | None = None,
        agent_chain: list[str] | None = None,
        complexity: str = AGENTIC_TASK,
        file_memory_context: dict[str, Any] | None = None,
        consolidation_summary: dict[str, Any] | None = None,
        dream_update_summary: dict[str, Any] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_search = tool_context.get("job_search") or {}
        fallback_notice = job_search.get("fallback_notice")
        if source == "fallback_rule" and issues:
            fallback_notice = issues[0]
        metadata = {
            "action": action,
            "assistant_type": AI_ASSISTANT_TYPE,
            "request_id": request_id or new_request_id(),
            "agent_run_id": agent_run_id or new_agent_run_id("chat"),
            "agent_name": agent_name or turn.agent_name,
            "agent_chain": agent_chain or [turn.agent_name],
            "agent_pipeline": agent_pipeline or {},
            "eval_tags": build_eval_tags(assistant_type=AI_ASSISTANT_TYPE, intent=turn.intent, tools=turn.tools),
            "model": provider.model,
            "provider": provider.name,
            "source": source,
            "status": status,
            "intent": turn.intent,
            "tools": turn.tools,
            "complexity": complexity,
            "prompt_template_id": getattr(turn, "prompt_template_id", None),
            "prompt_template_version": getattr(turn, "prompt_template_version", None),
            "memory_files_used": [
                item.get("name")
                for item in list((file_memory_context or {}).get("files_used") or [])
                if item.get("name")
            ],
            "consolidation_summary": consolidation_summary or {"compacted": False},
            "dream_update_summary": dream_update_summary or {"updated_files": []},
            "validation_status": validation_status,
            "issues": issues,
            "first_token_latency_ms": first_token_latency_ms,
            "total_latency_ms": int((time.perf_counter() - started_at) * 1000),
            "delta_count": delta_count,
            "interrupted": interrupted,
            "source_kind": job_search.get("source_kind"),
            "fallback_notice": fallback_notice,
            "memory_scope": self._memory_scope(),
            "memory_used": memory_context or self._empty_memory_used(),
            "memory_updates": memory_updates or self._empty_memory_updates(),
            "memory_snapshot": self._memory_snapshot_for_metadata(
                memory_context=memory_context,
                memory_updates=memory_updates,
            ),
            "retrieval_summary": build_retrieval_summary(tool_context),
            "evidence_summary": build_chat_evidence_summary(tool_context),
            "safety_boundary": build_safety_boundary(assistant_type=AI_ASSISTANT_TYPE, tools=turn.tools),
            "tool_calls_summary": self._tool_calls_summary(tool_context),
            "knowledge_references": self._knowledge_references(tool_context),
            "citation_protocol": build_citation_protocol(
                tool_context=tool_context,
                memory_context=memory_context or self._empty_memory_used(),
                memory_updates=memory_updates or self._empty_memory_updates(),
            ),
            "recommendations": job_search.get("jobs", [])[:5],
            "suggested_actions": self._suggested_actions(turn=turn, tool_context=tool_context),
        }
        if extra_metadata:
            for key, value in extra_metadata.items():
                if key not in {"agent_name", "agent_chain", "prompt_template_id", "prompt_template_version", "model", "provider"}:
                    metadata[key] = value
        return metadata

    @staticmethod
    def _suggested_actions(*, turn, tool_context: dict[str, Any]) -> list[dict[str, str]]:
        """Build lightweight next actions so chat can drive the user workflow."""
        actions: list[dict[str, str]] = []
        job_search = tool_context.get("job_search") or {}
        resume = tool_context.get("resume_profile") or {}
        keyword = str(job_search.get("keyword") or "").strip()
        if not keyword and turn.intent == "job_search":
            keyword = "产品经理"

        if turn.intent == "job_search" or job_search:
            query = f"?keyword={quote_plus(keyword)}" if keyword else ""
            actions.append(
                {
                    "kind": "job_search",
                    "label": "去搜索相关岗位",
                    "href": f"/jobs{query}",
                    "description": "把刚才的方向转成可保存、可投递的岗位列表。",
                }
            )

        if turn.intent in {"resume_review", "career_coaching", "job_search"} or resume:
            actions.append(
                {
                    "kind": "resume_advice",
                    "label": "生成投递建议",
                    "href": "/chat?prompt=请根据我的默认简历生成投递建议",
                    "description": "基于当前简历整理投递优先级和修改方向。",
                }
            )

        actions.append(
            {
                "kind": "interview_start",
                "label": "开始模拟面试",
                "href": "/interview/start",
                "description": "选择岗位后进入岗位 × 简历面试练习。",
            }
        )

        unique: list[dict[str, str]] = []
        seen: set[str] = set()
        for action in actions:
            if action["kind"] in seen:
                continue
            seen.add(action["kind"])
            unique.append(action)
        return unique[:3]

    @staticmethod
    def _tool_calls_summary(tool_context: dict[str, Any]) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        if resume := tool_context.get("resume_profile"):
            summary.append({"name": "resume_profile", "available": bool(resume.get("available")), "score": resume.get("score")})
        if jobs := tool_context.get("job_search"):
            summary.append(
                {
                    "name": "job_search",
                    "result_count": jobs.get("total", 0),
                    "source_kind": jobs.get("source_kind"),
                    "fallback_notice": jobs.get("fallback_notice"),
                }
            )
        if applications := tool_context.get("application_list"):
            summary.append({"name": "application_list", "result_count": applications.get("total", 0)})
        if knowledge := tool_context.get("knowledge_search"):
            summary.append(
                {
                    "name": "knowledge_search",
                    "result_count": knowledge.get("total", 0),
                    "source": knowledge.get("source", "knowledge_rag"),
                    "fallback_notice": knowledge.get("fallback_notice"),
                    "retrieval_strategy": knowledge.get("retrieval_strategy"),
                    "retrieval_sufficient": knowledge.get("retrieval_sufficient"),
                    "query_count": len((knowledge.get("query_plan") or {}).get("queries") or []),
                }
            )
        return summary

    @staticmethod
    def _knowledge_references(tool_context: dict[str, Any]) -> dict[str, Any]:
        knowledge = tool_context.get("knowledge_search") or {}
        hits = list(knowledge.get("hits") or [])
        return {
            "count": len(hits),
            "source": knowledge.get("source"),
            "fallback_notice": knowledge.get("fallback_notice"),
            "retrieval_strategy": knowledge.get("retrieval_strategy"),
            "retrieval_sufficient": knowledge.get("retrieval_sufficient"),
            "citations": normalize_knowledge_citations(knowledge.get("citations") or []),
            "items": [
                {
                    "question": hit.get("question"),
                    "section_path": hit.get("section_path") or [],
                    "score": (hit.get("metadata") or {}).get("rerank_score", hit.get("score")),
                    "source_file": hit.get("source_file"),
                    "source_url": (hit.get("metadata") or {}).get("source_url"),
                    "repo_path": (hit.get("metadata") or {}).get("repo_path"),
                    "chunk_index": (hit.get("metadata") or {}).get("chunk_index"),
                    "retrieval_channel": (hit.get("metadata") or {}).get("retrieval_channel"),
                }
                for hit in hits[:5]
            ],
        }

    def _run_tools(self, *, user_id: str, intent: str, message: str, tools: list[str]) -> dict[str, Any]:
        return ChatToolExecutor(db=self.chat_repository.db).run(user_id=user_id, intent=intent, message=message, tools=tools)

    def _remember_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        intent: str,
        tools: list[str],
        status: str,
        tool_context: dict[str, Any],
        request_id: str,
        agent_run_id: str,
        user_message: str,
        assistant_message: str,
        action: str,
        file_memory_service: AIMemoryFileService | None = None,
        force_consolidation: bool = False,
    ) -> dict[str, Any]:
        """Archive AI-assistant turns into file memory; PostgreSQL keeps business sessions."""
        service = file_memory_service or AIMemoryFileService()
        try:
            if action == "send":
                service.append_session_message(
                    user_id=user_id,
                    session_id=session_id,
                    role="user",
                    content=user_message,
                    metadata={"intent": intent, "tools": tools, "request_id": request_id, "agent_run_id": agent_run_id},
                )
            service.append_session_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                metadata={"intent": intent, "tools": tools, "status": status, "request_id": request_id, "agent_run_id": agent_run_id},
            )
            consolidation = service.soft_consolidate(user_id=user_id, session_id=session_id, force=force_consolidation)
            dream = {"updated_files": [], "history_items_read": 0, "reason": "scheduled_or_manual"}
            context = service.read_context(user_id=user_id, session_id=session_id)
            public_context = service.public_context_metadata(context)
        except Exception:
            return {
                "assistant_type": AI_ASSISTANT_TYPE,
                "count": 0,
                "pending_count": 0,
                "confirmed_count": 0,
                "items": [],
                "storage": "runtime/ai_assistant_memory",
                "memory_snapshot": self._empty_memory_snapshot(),
                "error": "file_memory_update_failed",
            }

        return {
            "assistant_type": AI_ASSISTANT_TYPE,
            "count": public_context.get("count", 0),
            "pending_count": 0,
            "confirmed_count": 0,
            "items": public_context.get("items", []),
            "storage": "runtime/ai_assistant_memory",
            "memory_files": public_context.get("memory_files", []),
            "consolidation": consolidation,
            "dream": dream,
            "compaction": {"compacted": bool(consolidation.get("compacted")), "count": int(consolidation.get("message_count") or 0)},
            "memory_snapshot": public_context.get("memory_snapshot") or self._empty_memory_snapshot(),
        }

    def _load_assistant_memory(self, *, user_id: str) -> dict[str, Any]:
        """Load AI-assistant memories only; interview memories are intentionally invisible here."""
        try:
            memories = AssistantMemoryRepository(self.chat_repository.db).list_active(
                user_id=user_id,
                assistant_type=AI_ASSISTANT_TYPE,
                limit=12,
            )
        except Exception:
            self.chat_repository.db.rollback()
            return {**self._empty_memory_used(), "error": "memory_load_failed"}
        items = [self._memory_item_summary(memory) for memory in memories]
        return {
            "assistant_type": AI_ASSISTANT_TYPE,
            "count": len(items),
            "items": items,
            "memory_snapshot": self._read_assistant_memory_snapshot(user_id=user_id),
        }

    def _load_assistant_memory_snapshot_content(self, *, user_id: str) -> str:
        try:
            snapshot = AssistantMemoryMarkdownService().read_snapshot(user_id=user_id, assistant_type=AI_ASSISTANT_TYPE)
        except Exception:
            return ""
        return str(snapshot.get("content") or "") if snapshot.get("available") else ""

    def _read_assistant_memory_snapshot(self, *, user_id: str) -> dict[str, Any]:
        try:
            snapshot = AssistantMemoryMarkdownService().read_snapshot(user_id=user_id, assistant_type=AI_ASSISTANT_TYPE)
        except Exception:
            return {**self._empty_memory_snapshot(), "error": "memory_snapshot_load_failed"}
        return AssistantMemoryMarkdownService.public_metadata(snapshot)

    def _refresh_assistant_memory_snapshot(self, *, user_id: str) -> dict[str, Any]:
        try:
            snapshot = AssistantMemoryMarkdownService().export_snapshot(
                db=self.chat_repository.db,
                user_id=user_id,
                assistant_type=AI_ASSISTANT_TYPE,
            )
        except Exception:
            self.chat_repository.db.rollback()
            return {**self._empty_memory_snapshot(), "error": "memory_snapshot_export_failed"}
        return AssistantMemoryMarkdownService.public_metadata(snapshot)

    @staticmethod
    def _memory_scope() -> dict[str, Any]:
        return {
            "short_term": "chat_sessions",
            "long_term": "runtime/ai_assistant_memory",
            "shared_fact_sources": ["resumes", "jobs", "applications", "users"],
        }

    @staticmethod
    def _empty_memory_used() -> dict[str, Any]:
        return {
            "assistant_type": AI_ASSISTANT_TYPE,
            "count": 0,
            "items": [],
            "compaction": {"compacted": False, "count": 0},
            "memory_snapshot": ChatService._empty_memory_snapshot(),
        }

    @staticmethod
    def _empty_memory_updates() -> dict[str, Any]:
        return {
            "assistant_type": AI_ASSISTANT_TYPE,
            "count": 0,
            "pending_count": 0,
            "confirmed_count": 0,
            "items": [],
            "memory_snapshot": ChatService._empty_memory_snapshot(),
        }

    @staticmethod
    def _empty_memory_snapshot() -> dict[str, Any]:
        return {
            "available": False,
            "assistant_type": AI_ASSISTANT_TYPE,
            "path": None,
            "item_count": 0,
            "char_count": 0,
        }

    @staticmethod
    def _memory_snapshot_for_metadata(
        *,
        memory_context: dict[str, Any] | None,
        memory_updates: dict[str, Any] | None,
    ) -> dict[str, Any]:
        snapshot = (memory_updates or {}).get("memory_snapshot") or (memory_context or {}).get("memory_snapshot")
        if snapshot:
            return AssistantMemoryMarkdownService.public_metadata(snapshot)
        return ChatService._empty_memory_snapshot()

    @staticmethod
    def _memory_item_summary(memory: dict[str, Any]) -> dict[str, Any]:
        summary = {
            "key": memory.get("key"),
            "memory_kind": memory.get("memory_kind"),
            "scope_type": memory.get("scope_type"),
            "summary": memory.get("summary"),
            "confidence": memory.get("confidence"),
            "source": memory.get("source"),
            "source_ref": memory.get("source_ref") or {},
        }
        if (memory.get("compaction") or {}).get("compacted"):
            summary["compaction"] = memory.get("compaction")
        return summary

    @staticmethod
    def _memory_compaction_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        compactions = [item.get("compaction") or {} for item in items if (item.get("compaction") or {}).get("compacted")]
        return {
            "compacted": bool(compactions),
            "count": sum(int(item.get("count") or 0) for item in compactions),
        }

    @staticmethod
    def _job_search_memory_summary(tool_context: dict[str, Any]) -> dict[str, Any] | None:
        job_search = tool_context.get("job_search") or {}
        if not job_search:
            return None
        keyword = job_search.get("keyword")
        city = job_search.get("city")
        skills = list(job_search.get("skills") or [])[:8]
        if not keyword and not city and not skills:
            return None
        summary_parts = []
        if keyword:
            summary_parts.append(f"方向 {keyword}")
        if city:
            summary_parts.append(f"城市 {city}")
        if skills:
            summary_parts.append(f"技能 {', '.join(skills)}")
        return {
            "keyword": keyword,
            "city": city,
            "experience": job_search.get("experience"),
            "skills": skills,
            "source_kind": job_search.get("source_kind"),
            "summary": "最近岗位搜索偏好：" + "；".join(summary_parts),
        }

    @staticmethod
    def _keyword_from_message(message: str) -> str | None:
        return keyword_from_message(message)

    @staticmethod
    def _city_from_message(message: str) -> str | None:
        return city_from_message(message)

    def _load_or_create_session(self, *, user_id: str, session_id: str | None):
        if session_id:
            session = self.chat_repository.get_by_id(session_id=session_id, user_id=user_id)
            if session is None:
                raise ChatServiceError(status_code=404, code=6002, message="Chat session not found")
            return session

        return self.chat_repository.create(
            user_id=user_id,
            messages=[],
            agent_states={self.supervisor.agent_name: "thinking"},
            last_agent=self.supervisor.agent_name,
            token_count=0,
        )

    @staticmethod
    def encode_sse(events: list[dict[str, Any]]) -> str:
        return "".join(encode_sse_event(event) for event in events)
