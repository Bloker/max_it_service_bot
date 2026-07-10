"""Runtime-сессии ввода заметки специалиста по заявке."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass(slots=True)
class KnowledgeCommentSession:
    """Ожидающий ввод внутренней заметки по заявке."""

    ticket_id: str
    actor_user_id: int
    actor_name: str
    started_at: datetime
    step: str = "waiting_title"
    group_chat_id: int | None = None
    prompt_message_id: str | None = None
    scope_id: int | None = None
    hotel_id: int | None = None
    category_id: int | None = None
    location_id: int | None = None
    location_display: str | None = None
    title: str = ""
    session_id: str = ""


class KnowledgeCommentSessionService:
    """Хранит активные сессии ввода заметки специалиста."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[int, KnowledgeCommentSession] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def start(
        self,
        *,
        actor_user_id: int,
        actor_name: str,
        ticket_id: str,
        group_chat_id: int | None = None,
        prompt_message_id: str | None = None,
        scope_id: int | None = None,
        hotel_id: int | None = None,
        category_id: int | None = None,
        location_id: int | None = None,
        location_display: str | None = None,
    ) -> KnowledgeCommentSession:
        """Переводит специалиста в режим ожидания заметки."""

        session = KnowledgeCommentSession(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            started_at=datetime.now(tz=timezone.utc),
            group_chat_id=group_chat_id,
            prompt_message_id=prompt_message_id,
            scope_id=scope_id,
            hotel_id=hotel_id,
            category_id=category_id,
            location_id=location_id,
            location_display=location_display,
            session_id=uuid4().hex,
        )
        self._sessions[actor_user_id] = session
        return session

    def get(self, actor_user_id: int) -> KnowledgeCommentSession | None:
        """Возвращает активную сессию специалиста."""

        self.cleanup_expired()
        return self._sessions.get(actor_user_id)

    def get_by_ticket(self, ticket_id: str) -> KnowledgeCommentSession | None:
        """Возвращает активную сессию по заявке."""

        self.cleanup_expired()
        for session in self._sessions.values():
            if session.ticket_id == ticket_id:
                return session
        return None

    def set_prompt_message_id(self, actor_user_id: int, prompt_message_id: str | None) -> None:
        """Сохраняет message_id служебного prompt."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return
        session.prompt_message_id = str(prompt_message_id) if prompt_message_id else None

    def set_title(self, actor_user_id: int, title: str) -> KnowledgeCommentSession | None:
        """Сохраняет тему заметки и переводит к вводу текста."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return None
        session.title = title
        session.step = "waiting_body"
        return session

    def finish(self, actor_user_id: int) -> KnowledgeCommentSession | None:
        """Завершает сессию специалиста."""

        return self._sessions.pop(actor_user_id, None)

    def cancel(self, actor_user_id: int) -> KnowledgeCommentSession | None:
        """Отменяет сессию специалиста."""

        return self.finish(actor_user_id)

    def reset(self, actor_user_id: int) -> None:
        """Сбрасывает активную сессию без результата."""

        self._sessions.pop(actor_user_id, None)

    def cleanup_expired(self) -> int:
        """Удаляет устаревшие сессии."""

        now = datetime.now(tz=timezone.utc)
        expired_ids = [
            actor_id
            for actor_id, session in self._sessions.items()
            if now - session.started_at > self._ttl
        ]
        for actor_id in expired_ids:
            self._sessions.pop(actor_id, None)
        return len(expired_ids)
