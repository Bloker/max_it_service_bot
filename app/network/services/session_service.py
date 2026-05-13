"""Сервис состояния сетевых инструментов в диалоге."""

from dataclasses import dataclass


@dataclass(slots=True)
class NetworkSession:
    """Состояние выбранного сетевого инструмента в личном диалоге."""

    pending_tool: str | None = None
    step: str = "idle"


class NetworkSessionService:
    """Хранит краткоживущие состояния сетевых инструментов по user_id."""

    def __init__(self) -> None:
        self._sessions: dict[int, NetworkSession] = {}

    def get(self, user_id: int) -> NetworkSession:
        return self._sessions.setdefault(user_id, NetworkSession())

    def expect_target(self, user_id: int, tool: str) -> None:
        """Переводит пользователя в ожидание цели для выбранного инструмента."""

        session = self.get(user_id)
        session.pending_tool = tool
        session.step = "awaiting_target"

    def reset(self, user_id: int) -> None:
        self._sessions[user_id] = NetworkSession()

    def mark_processed(self, user_id: int) -> None:
        """Сбрасывает инструмент после обработки разового ввода."""

        session = self.get(user_id)
        session.pending_tool = None
        session.step = "cooldown"
