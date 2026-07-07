import unittest

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.repositories.location_repository import (
    HotelRef,
    IssueCategoryRef,
    LocationRef,
)
from app.helpdesk.services.location_service import LocationService
from app.helpdesk.services.room_ticket_context_service import RoomTicketContextService


class RoomTicketContextServiceTests(unittest.TestCase):
    def test_identifies_jamaica_user_by_default_hotel(self) -> None:
        repository = _FakeLocationRepository()
        service = RoomTicketContextService(
            locations=LocationService(repository),
            context_repository=_FakeContextRepository(),
        )

        self.assertTrue(service.is_jamaica_user(101))
        self.assertFalse(service.is_jamaica_user(202))

    def test_location_categories_include_other_category(self) -> None:
        repository = _FakeLocationRepository()
        service = RoomTicketContextService(
            locations=LocationService(repository),
            context_repository=_FakeContextRepository(),
        )

        categories = service.list_location_categories(1)

        self.assertEqual([item.code for item in categories], ["tv", "other"])
        self.assertEqual(repository.last_requires_location, None)

    def test_save_and_read_context_through_repository(self) -> None:
        context_repository = _FakeContextRepository()
        service = RoomTicketContextService(
            locations=LocationService(_FakeLocationRepository()),
            context_repository=context_repository,
        )
        context = RoomTicketContext(
            ticket_key="T-00001",
            hotel_id=1,
            location_id=2,
            issue_category_id=3,
            room_number_snapshot="101",
            location_display_snapshot="Корпус 1, номер 101",
            category_snapshot="ТВ",
        )

        saved = service.save_context(context)
        loaded = service.get_context("T-00001")

        self.assertEqual(context, saved)
        self.assertEqual(context, loaded)


class _FakeLocationRepository:
    def __init__(self) -> None:
        self.last_requires_location = "not-called"

    def find_hotel_by_code(self, code: str):
        return HotelRef(id=1, code="jamaica", name="Jamaica")

    def find_user_default_hotel(self, user_id: int):
        if user_id == 101:
            return HotelRef(id=1, code="jamaica", name="Jamaica")
        return HotelRef(id=2, code="other", name="Other")

    def find_location_by_room_number(self, hotel_id: int, room_number: str):
        return LocationRef(
            id=10,
            hotel_id=hotel_id,
            location_code=f"room-{room_number}",
            location_type="room",
            building_name="Корпус 1",
            room_number=room_number,
            display_name=f"Корпус 1, номер {room_number}",
        )

    def list_issue_categories_for_hotel(self, hotel_id: int, *, requires_location=None):
        self.last_requires_location = requires_location
        return (
            IssueCategoryRef(1, "tv", "ТВ", True, 10),
            IssueCategoryRef(2, "other", "Прочее", False, 50),
        )


class _FakeContextRepository:
    def __init__(self) -> None:
        self.contexts: dict[str, RoomTicketContext] = {}

    def save(self, context: RoomTicketContext) -> RoomTicketContext:
        self.contexts[context.ticket_key] = context
        return context

    def get_by_ticket_key(self, ticket_key: str) -> RoomTicketContext | None:
        return self.contexts.get(ticket_key)


if __name__ == "__main__":
    unittest.main()
