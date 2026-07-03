"""Runtime-сессии запроса уточнения по заявке."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class ClarificationSession:
    """Ожидающий ввод вопроса от специалиста."""

    ticket_id: str
    actor_user_id: int
    actor_name: str
    started_at: datetime
    group_chat_id: int | None = None
    prompt_message_id: str | None = None
    session_id: str = ""


class ClarificationSessionService:
    """Хранит активные запросы уточнения до следующего сообщения."""

    def __init__(self) -> None:
        self._sessions: dict[int, ClarificationSession] = {}

    def start(
        self,
        *,
        actor_user_id: int,
        actor_name: str,
        ticket_id: str,
        group_chat_id: int | None = None,
        prompt_message_id: str | None = None,
    ) -> ClarificationSession:
        """Переводит специалиста в ожидание текста вопроса."""

        session = ClarificationSession(
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
        """Сохраняет идентификатор служебного prompt-сообщения."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return
        session.prompt_message_id = str(prompt_message_id) if prompt_message_id else None

    def get(self, actor_user_id: int) -> ClarificationSession | None:
        """Возвращает активную сессию специалиста."""

        return self._sessions.get(actor_user_id)

    def get_by_ticket(self, ticket_id: str) -> ClarificationSession | None:
        """Возвращает активную сессию по заявке."""

        for session in self._sessions.values():
            if session.ticket_id == ticket_id:
                return session
        return None

    def pop(self, actor_user_id: int) -> ClarificationSession | None:
        """Завершает и возвращает активную сессию специалиста."""

        return self._sessions.pop(actor_user_id, None)

    def reset(self, actor_user_id: int) -> None:
        """Сбрасывает активную сессию специалиста."""

        self._sessions.pop(actor_user_id, None)
