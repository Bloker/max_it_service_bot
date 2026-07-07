"""Контракт чтения hotel/location справочников HelpDesk."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HotelRef:
    """Краткая ссылка на отель."""

    id: int
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class LocationRef:
    """Краткая ссылка на объект обслуживания."""

    id: int
    hotel_id: int
    location_code: str
    location_type: str
    building_name: str | None
    room_number: str
    display_name: str


@dataclass(frozen=True, slots=True)
class IssueCategoryRef:
    """Краткая ссылка на hotel-specific категорию заявки."""

    id: int
    code: str
    title: str
    requires_location: bool
    sort_order: int


class LocationRepository(Protocol):
    """Read-only repository для hotel-specific справочников."""

    def find_hotel_by_code(self, code: str) -> HotelRef | None: ...

    def find_user_default_hotel(self, user_id: int) -> HotelRef | None: ...

    def find_location_by_room_number(self, hotel_id: int, room_number: str) -> LocationRef | None: ...

    def list_issue_categories_for_hotel(
        self,
        hotel_id: int,
        *,
        requires_location: bool | None = None,
    ) -> tuple[IssueCategoryRef, ...]: ...
