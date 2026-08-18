"""Runtime-сессии добавления информации пользователем к заявке."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class UserAdditionSession:
    """Ожидающий ввод дополнения владельца заявки."""

    ticket_id: str
    user_id: int
    prompt_message_id: str | None
    started_at: datetime
    session_id: str


class UserAdditionSessionService:
    """Хранит одну активную сессию дополнения на пользователя."""

    def __init__(self) -> None:
        self._sessions: dict[int, UserAdditionSession] = {}

    def start(
        self,
        *,
        user_id: int,
        ticket_id: str,
        prompt_message_id: str | None = None,
    ) -> UserAdditionSession:
        session = UserAdditionSession(
            ticket_id=ticket_id,
            user_id=user_id,
            prompt_message_id=prompt_message_id,
            started_at=datetime.now(tz=timezone.utc),
            session_id=uuid4().hex,
        )
        self._sessions[user_id] = session
        return session

    def get(self, user_id: int) -> UserAdditionSession | None:
        return self._sessions.get(user_id)

    def set_prompt_message_id(self, user_id: int, message_id: str | None) -> None:
        session = self._sessions.get(user_id)
        if session is not None:
            session.prompt_message_id = message_id

    def reset(self, user_id: int) -> UserAdditionSession | None:
        return self._sessions.pop(user_id, None)
