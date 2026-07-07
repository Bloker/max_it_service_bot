"""Модели hotel-specific контекста заявки по номеру."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RoomTicketContext:
    """Снимок номера, объекта и категории, привязанный к заявке."""

    ticket_key: str
    hotel_id: int
    location_id: int | None = None
    issue_category_id: int | None = None
    room_number_snapshot: str | None = None
    location_display_snapshot: str | None = None
    category_snapshot: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
