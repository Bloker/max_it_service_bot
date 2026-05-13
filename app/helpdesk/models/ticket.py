"""Доменная модель заявки HelpDesk."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class TicketStatus(StrEnum):
    """Статусы жизненного цикла заявки HelpDesk."""

    NEW = "новое"
    IN_PROGRESS = "в работе"
    WAITING_USER = "ожидает пользователя"
    CLOSED = "закрыто"


@dataclass(slots=True)
class Ticket:
    """Доменная модель заявки HelpDesk."""

    id: str
    user_id: int
    category: str
    text: str
    status: TicketStatus = TicketStatus.NEW
    assigned_to: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # Дополнительный контекст заявителя и исполнителя.
    requester_name: str | None = None
    assignee_name: str | None = None
    requester_phone: str | None = None
    requester_department: str | None = None

    # Совместимые псевдонимы для старых обработчиков и сервисов.
    @property
    def ticket_id(self) -> str:
        """Возвращает публичный идентификатор заявки."""

        return self.id

    @property
    def requester_user_id(self) -> int:
        """Возвращает MAX ID автора заявки."""

        return self.user_id

    @property
    def assignee_user_id(self) -> int | None:
        """Возвращает MAX ID назначенного исполнителя."""

        return self.assigned_to
