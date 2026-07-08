"""Сервис истории заявок по номеру/домику."""

import logging

from app.helpdesk.models.room_ticket_history import RoomTicketHistoryItem
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.repositories.room_ticket_context_repository import (
    RoomTicketContextRepository,
)


ROOM_HISTORY_LIMIT = 10

logger = logging.getLogger(__name__)


class RoomHistoryService:
    """Возвращает историю заявок по location_id."""

    def __init__(self, repository: RoomTicketContextRepository | None = None) -> None:
        self._repository = repository

    def get_context_by_ticket_key(self, ticket_key: str) -> RoomTicketContext | None:
        """Возвращает контекст заявки, если repository подключен."""

        if self._repository is None:
            return None
        try:
            return self._repository.get_by_ticket_key(ticket_key)
        except Exception:
            logger.exception("Failed to read room history context: ticket_id=%s", ticket_key)
            return None

    def list_recent_tickets_for_location(
        self,
        hotel_id: int,
        location_id: int,
        *,
        exclude_ticket_key: str | None = None,
        limit: int = ROOM_HISTORY_LIMIT,
    ) -> list[RoomTicketHistoryItem]:
        """Возвращает недавние заявки по тому же объекту."""

        if self._repository is None:
            return []
        try:
            return self._repository.list_recent_tickets_for_location(
                hotel_id,
                location_id,
                exclude_ticket_key=exclude_ticket_key,
                limit=limit,
            )
        except Exception:
            logger.exception(
                "Failed to read room history list: hotel_id=%s location_id=%s exclude_ticket_key=%s",
                hotel_id,
                location_id,
                exclude_ticket_key,
            )
            return []
