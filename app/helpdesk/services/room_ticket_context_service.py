"""Сервис контекста заявок по номеру для hotel-specific flow."""

import logging

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.repositories.location_repository import IssueCategoryRef, LocationRef
from app.helpdesk.repositories.room_ticket_context_repository import (
    RoomTicketContextRepository,
)
from app.helpdesk.services.location_service import LocationService

logger = logging.getLogger(__name__)


class RoomTicketContextService:
    """Связывает пользователя, номер, категорию и заявку."""

    def __init__(
        self,
        *,
        locations: LocationService,
        context_repository: RoomTicketContextRepository | None = None,
        hotel_code: str = "jamaica",
    ) -> None:
        self._locations = locations
        self._context_repository = context_repository
        self._hotel_code = hotel_code

    def is_jamaica_user(self, user_id: int) -> bool:
        """Проверяет, привязан ли пользователь к отелю Jamaica."""

        hotel = self._locations.find_user_default_hotel(user_id)
        return bool(hotel and hotel.code == self._hotel_code)

    def find_user_hotel(self, user_id: int):
        """Возвращает активный отель пользователя."""

        return self._locations.find_user_default_hotel(user_id)

    def find_location(self, hotel_id: int, room_number: str) -> LocationRef | None:
        """Ищет номер или домик в справочнике отеля."""

        return self._locations.find_location_by_room_number(hotel_id, room_number)

    def list_location_categories(self, hotel_id: int) -> tuple[IssueCategoryRef, ...]:
        """Возвращает все категории, включенные для заявки по номеру."""

        return self._locations.list_issue_categories_for_hotel(
            hotel_id,
            requires_location=None,
        )

    def find_location_category(
        self,
        hotel_id: int,
        category_code: str,
    ) -> IssueCategoryRef | None:
        """Находит категорию заявки по номеру по стабильному коду."""

        normalized_code = category_code.strip().lower()
        return next(
            (
                category
                for category in self.list_location_categories(hotel_id)
                if category.code.strip().lower() == normalized_code
            ),
            None,
        )

    def find_other_category(self, hotel_id: int) -> IssueCategoryRef | None:
        """Находит категорию 'Прочее' для заявки без номера."""

        for category in self._locations.list_issue_categories_for_hotel(
            hotel_id,
            requires_location=False,
        ):
            if category.code == "other":
                return category
        for category in self._locations.list_issue_categories_for_hotel(
            hotel_id,
            requires_location=None,
        ):
            if category.code == "other":
                return category
        return None

    def save_context(self, context: RoomTicketContext) -> RoomTicketContext | None:
        """Сохраняет контекст без падения основного сценария заявки."""

        if self._context_repository is None:
            return None
        try:
            return self._context_repository.save(context)
        except Exception:
            logger.exception(
                "Failed to save room ticket context: ticket_id=%s",
                context.ticket_key,
            )
            return None

    def get_context(self, ticket_key: str) -> RoomTicketContext | None:
        """Возвращает контекст карточки, если хранилище подключено."""

        if self._context_repository is None:
            return None
        try:
            return self._context_repository.get_by_ticket_key(ticket_key)
        except Exception:
            logger.exception("Failed to read room ticket context: ticket_id=%s", ticket_key)
            return None
