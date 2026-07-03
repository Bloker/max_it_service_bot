"""Runtime-сессии ответа пользователя по заявке."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class UserReplySession:
    """Ожидающий ввод ответа от пользователя."""

    ticket_id: str
    user_id: int
    started_at: datetime
    session_id: str


class UserReplySessionService:
    """Хранит ожидание ответа пользователя до следующего сообщения."""

    def __init__(self) -> None:
        self._sessions: dict[int, UserReplySession] = {}

    def start(self, *, user_id: int, ticket_id: str) -> UserReplySession:
        """Переводит пользователя в ожидание текста ответа."""

        session = UserReplySession(
            ticket_id=ticket_id,
            user_id=user_id,
            started_at=datetime.now(tz=timezone.utc),
            session_id=uuid4().hex,
        )
        self._sessions[user_id] = session
        return session

    def get(self, user_id: int) -> UserReplySession | None:
        """Возвращает активную сессию пользователя."""

        return self._sessions.get(user_id)

    def reset(self, user_id: int) -> None:
        """Сбрасывает активную сессию пользователя."""

        self._sessions.pop(user_id, None)
