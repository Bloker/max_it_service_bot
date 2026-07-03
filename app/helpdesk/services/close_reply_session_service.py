"""Runtime-сессии закрытия заявки с ответом пользователю."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass(slots=True)
class CloseReplySession:
    """Ожидающий ввод текста ответа при закрытии заявки."""

    ticket_id: str
    actor_user_id: int
    actor_name: str
    started_at: datetime
    group_chat_id: int | None = None
    prompt_message_id: str | None = None
    session_id: str = ""


class CloseReplySessionService:
    """Хранит активные close-with-reply сессии специалистов."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[int, CloseReplySession] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def start(
        self,
        *,
        actor_user_id: int,
        actor_name: str,
        ticket_id: str,
        group_chat_id: int | None = None,
        prompt_message_id: str | None = None,
    ) -> CloseReplySession:
        """Переводит специалиста в ожидание текста закрытия."""

        session = CloseReplySession(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            started_at=datetime.now(tz=timezone.utc),
            group_chat_id=group_chat_id,
            prompt_message_id=prompt_message_id,
            session_id=uuid4().hex,
        )
        self._sessions[actor_user_id] = session
        return session

    def set_prompt_message_id(self, actor_user_id: int, prompt_message_id: str | None) -> None:
        """Сохраняет message_id служебного prompt."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return
        session.prompt_message_id = str(prompt_message_id) if prompt_message_id else None

    def get(self, actor_user_id: int) -> CloseReplySession | None:
        """Возвращает активную сессию специалиста."""

        self.cleanup_expired()
        return self._sessions.get(actor_user_id)

    def get_by_ticket(self, ticket_id: str) -> CloseReplySession | None:
        """Возвращает активную сессию по заявке."""

        self.cleanup_expired()
        for session in self._sessions.values():
            if session.ticket_id == ticket_id:
                return session
        return None

    def finish(self, actor_user_id: int) -> CloseReplySession | None:
        """Завершает сессию специалиста."""

        return self._sessions.pop(actor_user_id, None)

    def cancel(self, actor_user_id: int) -> CloseReplySession | None:
        """Отменяет сессию специалиста."""

        return self.finish(actor_user_id)

    def reset(self, actor_user_id: int) -> None:
        """Сбрасывает сессию специалиста без результата."""

        self._sessions.pop(actor_user_id, None)

    def cleanup_expired(self) -> int:
        """Удаляет устаревшие сессии и возвращает их количество."""

        now = datetime.now(tz=timezone.utc)
        expired_ids = [
            actor_id
            for actor_id, session in self._sessions.items()
            if now - session.started_at > self._ttl
        ]
        for actor_id in expired_ids:
            self._sessions.pop(actor_id, None)
        return len(expired_ids)
