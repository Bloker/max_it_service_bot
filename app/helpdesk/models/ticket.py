from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class TicketStatus(StrEnum):
    NEW = "новое"
    IN_PROGRESS = "в работе"
    WAITING_USER = "ожидает пользователя"
    CLOSED = "закрыто"


@dataclass(slots=True)
class Ticket:
    # Minimal stage-4 model
    id: str
    user_id: int
    category: str
    text: str
    status: TicketStatus = TicketStatus.NEW
    assigned_to: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # Optional useful context (non-critical)
    requester_name: str | None = None
    assignee_name: str | None = None
    requester_phone: str | None = None
    requester_department: str | None = None

    # Backward-compatible aliases for existing handlers/services
    @property
    def ticket_id(self) -> str:
        return self.id

    @property
    def requester_user_id(self) -> int:
        return self.user_id

    @property
    def assignee_user_id(self) -> int | None:
        return self.assigned_to
