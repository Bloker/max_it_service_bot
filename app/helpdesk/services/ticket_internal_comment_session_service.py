"""Сессии ввода внутренних комментариев специалиста."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class TicketInternalCommentSession:
    """Состояние ожидания внутреннего комментария по заявке."""

    ticket_id: str
    actor_user_id: int
    actor_name: str
    group_chat_id: int | None = None
    prompt_message_id: str | None = None
    hotel_id: int | None = None
    location_id: int | None = None
    location_display: str | None = None
    category_id: int | None = None
    category_title: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str = ""


class TicketInternalCommentSessionService:
    """Хранит активные сессии ввода внутренних комментариев в памяти процесса."""

    def __init__(self) -> None:
        self._sessions: dict[int, TicketInternalCommentSession] = {}

    def start(
        self,
        *,
        actor_user_id: int,
        actor_name: str,
        ticket_id: str,
        group_chat_id: int | None = None,
        hotel_id: int | None = None,
        location_id: int | None = None,
        location_display: str | None = None,
        category_id: int | None = None,
        category_title: str | None = None,
    ) -> TicketInternalCommentSession:
        """Создаёт или заменяет сессию одного специалиста."""

        session = TicketInternalCommentSession(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            group_chat_id=group_chat_id,
            hotel_id=hotel_id,
            location_id=location_id,
            location_display=location_display,
            category_id=category_id,
            category_title=category_title,
            session_id=uuid4().hex,
        )
        self._sessions[actor_user_id] = session
        return session

    def get(self, actor_user_id: int) -> TicketInternalCommentSession | None:
        """Возвращает сессию специалиста."""

        return self._sessions.get(actor_user_id)

    def get_by_ticket(self, ticket_id: str) -> TicketInternalCommentSession | None:
        """Возвращает активную сессию по заявке."""

        return next((item for item in self._sessions.values() if item.ticket_id == ticket_id), None)

    def set_prompt_message_id(
        self, actor_user_id: int, message_id: str | None
    ) -> TicketInternalCommentSession | None:
        """Запоминает ID временного сообщения-приглашения."""

        session = self.get(actor_user_id)
        if session is not None:
            session.prompt_message_id = message_id
        return session

    def finish(self, actor_user_id: int) -> TicketInternalCommentSession | None:
        """Завершает сессию после успешного сохранения."""

        return self._sessions.pop(actor_user_id, None)

    def cancel(self, actor_user_id: int) -> TicketInternalCommentSession | None:
        """Отменяет сессию специалиста."""

        return self.finish(actor_user_id)
