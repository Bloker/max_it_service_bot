"""Контракт хранения hotel-specific контекста заявки."""

from typing import Protocol

from app.helpdesk.models.room_ticket_context import RoomTicketContext


class RoomTicketContextRepository(Protocol):
    """Repository для таблицы helpdesk.ticket_context."""

    def save(self, context: RoomTicketContext) -> RoomTicketContext: ...

    def get_by_ticket_key(self, ticket_key: str) -> RoomTicketContext | None: ...
