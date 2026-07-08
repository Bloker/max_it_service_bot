"""Модели истории заявок по номеру или домику."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RoomTicketHistoryItem:
    """Краткая запись истории заявок для одного объекта."""

    ticket_key: str
    hotel_id: int
    location_id: int
    category_snapshot: str | None
    status: str | None
    created_at: datetime
    closed_at: datetime | None = None
