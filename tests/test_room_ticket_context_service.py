import unittest

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.repositories.location_repository import (
    HotelRef,
    IssueCategoryRef,
    LocationRef,
)
from app.helpdesk.services.location_service import LocationService
from app.helpdesk.services.room_ticket_context_service import RoomTicketContextService
from app.helpdesk.texts.formatters import format_room_context_object


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

        self.assertEqual(
            [item.code for item in categories],
            ["tv", "internet", "other"],
        )
        self.assertEqual(repository.last_requires_location, None)

    def test_finds_location_category_by_stable_code(self) -> None:
        service = RoomTicketContextService(
            locations=LocationService(_FakeLocationRepository()),
            context_repository=_FakeContextRepository(),
        )

        category = service.find_location_category(1, "INTERNET")

        self.assertIsNotNone(category)
        self.assertEqual(category.code, "internet")
        self.assertEqual(category.title, "Интернет")

    def test_location_lookup_supports_cottage_and_missing_room(self) -> None:
        service = RoomTicketContextService(
            locations=LocationService(_FakeLocationRepository()),
            context_repository=_FakeContextRepository(),
        )

        cottage = service.find_location(1, "15")

        self.assertIsNotNone(cottage)
        self.assertEqual(cottage.location_type, "cottage")
        self.assertEqual(cottage.display_name, "Домик 15")
        self.assertIsNone(service.find_location(1, "99999"))

    def test_general_wifi_context_renders_other_internet_object(self) -> None:
        self.assertEqual(
            format_room_context_object(
                room_number_snapshot=None,
                location_display_snapshot="Прочее",
                category_snapshot="Интернет",
            ),
            "Прочее (Интернет)",
        )

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
        if room_number == "99999":
            return None
        if room_number == "15":
            return LocationRef(
                id=15,
                hotel_id=hotel_id,
                location_code="cottage-15",
                location_type="cottage",
                building_name=None,
                room_number=room_number,
                display_name="Домик 15",
            )
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
            IssueCategoryRef(3, "internet", "Интернет", True, 30),
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
