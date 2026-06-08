from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession


class ChatSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, messages: list[dict], agent_states: dict, last_agent: str, token_count: int) -> ChatSession:
        session = ChatSession(
            user_id=user_id,
            messages=messages,
            agent_states=agent_states,
            last_agent=last_agent,
            token_count=token_count,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def append_turn(
        self,
        *,
        session: ChatSession,
        user_message: str,
        assistant_message: str,
        last_agent: str,
        agent_states: dict | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
        user_metadata: dict | None = None,
        assistant_metadata: dict | None = None,
    ) -> ChatSession:
        messages = list(session.messages or [])
        messages.extend(
            [
                {
                    "role": "user",
                    "content": user_message,
                    **({"id": user_message_id} if user_message_id else {}),
                    **({"metadata": user_metadata} if user_metadata else {}),
                },
                {
                    "role": "assistant",
                    "content": assistant_message,
                    **({"id": assistant_message_id} if assistant_message_id else {}),
                    **({"metadata": assistant_metadata} if assistant_metadata else {}),
                },
            ]
        )
        session.messages = messages
        session.agent_states = {**(session.agent_states or {}), **(agent_states or {})}
        session.last_agent = last_agent
        session.token_count = int(session.token_count or 0) + len(user_message) + len(assistant_message)
        session.updated_at = datetime.utcnow()
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def replace_last_assistant(
        self,
        *,
        session: ChatSession,
        assistant_message: str,
        last_agent: str,
        agent_states: dict | None = None,
        assistant_message_id: str | None = None,
        assistant_metadata: dict | None = None,
    ) -> ChatSession:
        messages = list(session.messages or [])
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "assistant":
                previous_content = str(messages[index].get("content") or "")
                messages[index] = {
                    **messages[index],
                    "content": assistant_message,
                    **({"id": assistant_message_id} if assistant_message_id else {}),
                    **({"metadata": assistant_metadata} if assistant_metadata else {}),
                }
                session.token_count = max(0, int(session.token_count or 0) - len(previous_content) + len(assistant_message))
                break
        else:
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message,
                    **({"id": assistant_message_id} if assistant_message_id else {}),
                    **({"metadata": assistant_metadata} if assistant_metadata else {}),
                }
            )
            session.token_count = int(session.token_count or 0) + len(assistant_message)

        session.messages = messages
        session.agent_states = {**(session.agent_states or {}), **(agent_states or {})}
        session.last_agent = last_agent
        session.updated_at = datetime.utcnow()
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def append_to_last_assistant(
        self,
        *,
        session: ChatSession,
        assistant_delta: str,
        last_agent: str,
        agent_states: dict | None = None,
        assistant_metadata: dict | None = None,
    ) -> ChatSession:
        messages = list(session.messages or [])
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "assistant":
                messages[index] = {
                    **messages[index],
                    "content": f"{messages[index].get('content') or ''}{assistant_delta}",
                    **({"metadata": assistant_metadata} if assistant_metadata else {}),
                }
                break
        else:
            messages.append({"role": "assistant", "content": assistant_delta, **({"metadata": assistant_metadata} if assistant_metadata else {})})

        session.messages = messages
        session.agent_states = {**(session.agent_states or {}), **(agent_states or {})}
        session.last_agent = last_agent
        session.token_count = int(session.token_count or 0) + len(assistant_delta)
        session.updated_at = datetime.utcnow()
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_by_id(self, *, session_id: str, user_id: str | None = None) -> ChatSession | None:
        stmt: Select[tuple[ChatSession]] = select(ChatSession).where(ChatSession.id == session_id)
        if user_id is not None:
            stmt = stmt.where(ChatSession.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def count_by_user_id(self, *, user_id: str) -> int:
        stmt = select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user_id)
        return int(self.db.execute(stmt).scalar_one())

    def list_by_user_id(self, *, user_id: str, limit: int = 5) -> list[ChatSession]:
        stmt: Select[tuple[ChatSession]] = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())
