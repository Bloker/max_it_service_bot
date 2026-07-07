"""Service layer для hotel/location справочников HelpDesk."""

from app.helpdesk.repositories.location_repository import (
    HotelRef,
    IssueCategoryRef,
    LocationRef,
    LocationRepository,
)
from app.helpdesk.services.jamaica_seed_data import normalize_room_number


class LocationService:
    """Read-only операции для будущего hotel-specific flow."""

    def __init__(self, repository: LocationRepository) -> None:
        self._repository = repository

    def find_hotel_by_code(self, code: str) -> HotelRef | None:
        """Возвращает отель по нормализованному коду."""

        return self._repository.find_hotel_by_code((code or "").strip().lower())

    def find_user_default_hotel(self, user_id: int) -> HotelRef | None:
        """Возвращает текущий отель пользователя."""

        return self._repository.find_user_default_hotel(user_id)

    def find_location_by_room_number(self, hotel_id: int, room_number: str) -> LocationRef | None:
        """Ищет активную location по номеру, не приводя номер к int."""

        return self._repository.find_location_by_room_number(
            hotel_id,
            normalize_room_number(room_number),
        )

    def list_issue_categories_for_hotel(
        self,
        hotel_id: int,
        *,
        requires_location: bool | None = None,
    ) -> tuple[IssueCategoryRef, ...]:
        """Возвращает включенные категории для отеля."""

        return self._repository.list_issue_categories_for_hotel(
            hotel_id,
            requires_location=requires_location,
        )
