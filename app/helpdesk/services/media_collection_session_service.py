"""In-memory сессии сбора текста и media с окном тишины."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


STATE_TICKET_COMMENT = "collecting_ticket_comment"
STATE_KNOWLEDGE_ARTICLE = "collecting_knowledge_article"
STATE_CLOSE_REPLY = "collecting_close_reply"


@dataclass(slots=True)
class MediaCollectionSession:
    """Состояние 15-секундного окна сбора сообщений."""

    actor_user_id: int
    chat_id: int
    state: str
    ticket_key: str | None = None
    group_message_id: str | None = None
    scope_id: int | None = None
    scope_title: str | None = None
    hotel_id: int | None = None
    category_id: int | None = None
    category_title: str | None = None
    location_id: int | None = None
    location_display: str | None = None
    title: str | None = None
    body_parts: list[str] = field(default_factory=list)
    pending_media: list[Any] = field(default_factory=list)
    transient_message_ids: list[str] = field(default_factory=list)
    prompt_message_id: str | None = None
    source_kind: str = "manual"
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_message_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    deadline_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    session_id: str = field(default_factory=lambda: uuid4().hex)
    finalize_task: asyncio.Task[None] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def body_text(self) -> str:
        parts = [item.strip() for item in self.body_parts if item and item.strip()]
        return "\n".join(parts).strip()


class MediaCollectionSessionService:
    """Хранит активные окна сбора для комментариев и KB-заметок."""

    def __init__(self, collection_window_sec: int = 15) -> None:
        self._sessions: dict[int, MediaCollectionSession] = {}
        self._window = timedelta(seconds=collection_window_sec)

    def start(
        self,
        *,
        actor_user_id: int,
        chat_id: int,
        state: str,
        ticket_key: str | None = None,
        group_message_id: str | None = None,
        scope_id: int | None = None,
        scope_title: str | None = None,
        hotel_id: int | None = None,
        category_id: int | None = None,
        category_title: str | None = None,
        location_id: int | None = None,
        location_display: str | None = None,
        title: str | None = None,
        prompt_message_id: str | None = None,
        source_kind: str = "manual",
        transient_message_ids: list[str] | None = None,
    ) -> MediaCollectionSession:
        now = datetime.now(tz=timezone.utc)
        session = MediaCollectionSession(
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            state=state,
            ticket_key=ticket_key,
            group_message_id=group_message_id,
            scope_id=scope_id,
            scope_title=scope_title,
            hotel_id=hotel_id,
            category_id=category_id,
            category_title=category_title,
            location_id=location_id,
            location_display=location_display,
            title=title,
            transient_message_ids=[item for item in (transient_message_ids or []) if item],
            prompt_message_id=prompt_message_id,
            source_kind=source_kind,
            created_at=now,
            last_message_at=now,
            deadline_at=now + self._window,
        )
        self.cancel(actor_user_id)
        self._sessions[actor_user_id] = session
        return session

    def get(self, actor_user_id: int) -> MediaCollectionSession | None:
        return self._sessions.get(actor_user_id)

    def append(
        self,
        actor_user_id: int,
        *,
        text: str | None = None,
        media: list[Any] | None = None,
        warnings: list[str] | None = None,
        transient_message_ids: list[str] | None = None,
    ) -> MediaCollectionSession | None:
        session = self._sessions.get(actor_user_id)
        if session is None:
            return None
        if text is not None and text.strip():
            session.body_parts.append(text.strip())
        if media:
            session.pending_media.extend(media)
        if transient_message_ids:
            for message_id in transient_message_ids:
                if message_id and message_id not in session.transient_message_ids:
                    session.transient_message_ids.append(message_id)
        if warnings:
            session.warnings.extend(warnings)
        now = datetime.now(tz=timezone.utc)
        session.last_message_at = now
        session.deadline_at = now + self._window
        return session

    def set_finalize_task(self, actor_user_id: int, task: asyncio.Task[None] | None) -> None:
        session = self._sessions.get(actor_user_id)
        if session is None:
            return
        if session.finalize_task and not session.finalize_task.done() and session.finalize_task is not task:
            session.finalize_task.cancel()
        session.finalize_task = task

    def pop_if_due(self, actor_user_id: int, session_id: str) -> MediaCollectionSession | None:
        session = self._sessions.get(actor_user_id)
        if session is None or session.session_id != session_id:
            return None
        if datetime.now(tz=timezone.utc) < session.deadline_at:
            return None
        return self.finish(actor_user_id)

    def finish(self, actor_user_id: int) -> MediaCollectionSession | None:
        session = self._sessions.pop(actor_user_id, None)
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if (
            session
            and session.finalize_task
            and not session.finalize_task.done()
            and session.finalize_task is not current_task
        ):
            session.finalize_task.cancel()
        return session

    def cancel(self, actor_user_id: int) -> MediaCollectionSession | None:
        return self.finish(actor_user_id)
