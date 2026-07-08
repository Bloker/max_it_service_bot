"""Контракт хранения hotel-specific контекста заявки."""

from typing import Protocol

from app.helpdesk.models.room_ticket_history import RoomTicketHistoryItem
from app.helpdesk.models.room_ticket_context import RoomTicketContext


class RoomTicketContextRepository(Protocol):
    """Repository для таблицы helpdesk.ticket_context."""

    def save(self, context: RoomTicketContext) -> RoomTicketContext: ...

    def get_by_ticket_key(self, ticket_key: str) -> RoomTicketContext | None: ...

    def list_recent_tickets_for_location(
        self,
        hotel_id: int,
        location_id: int,
        *,
        exclude_ticket_key: str | None = None,
        limit: int = 10,
    ) -> list[RoomTicketHistoryItem]: ...
