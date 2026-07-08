from datetime import datetime, timedelta, timezone
import unittest

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.room_ticket_history import RoomTicketHistoryItem
from app.helpdesk.services.room_history_service import (
    ROOM_HISTORY_LIMIT,
    RoomHistoryService,
)


class FakeRoomHistoryRepository:
    def __init__(
        self,
        *,
        context: RoomTicketContext | None = None,
        items: list[RoomTicketHistoryItem] | None = None,
    ) -> None:
        self.context = context
        self.items = items or []
        self.calls: list[dict] = []

    def get_by_ticket_key(self, ticket_key: str) -> RoomTicketContext | None:
        self.calls.append({"method": "get_by_ticket_key", "ticket_key": ticket_key})
        return self.context

    def list_recent_tickets_for_location(
        self,
        hotel_id: int,
        location_id: int,
        *,
        exclude_ticket_key: str | None = None,
        limit: int = 10,
    ) -> list[RoomTicketHistoryItem]:
        self.calls.append(
            {
                "method": "list_recent_tickets_for_location",
                "hotel_id": hotel_id,
                "location_id": location_id,
                "exclude_ticket_key": exclude_ticket_key,
                "limit": limit,
            }
        )
        filtered = [
            item
            for item in self.items
            if item.hotel_id == hotel_id
            and item.location_id == location_id
            and (exclude_ticket_key is None or item.ticket_key != exclude_ticket_key)
        ]
        return filtered[:limit]


class RoomHistoryServiceTests(unittest.TestCase):
    def test_get_context_by_ticket_key_returns_repository_value(self) -> None:
        context = RoomTicketContext(ticket_key="T-00088", hotel_id=1, location_id=12)
        repository = FakeRoomHistoryRepository(context=context)
        service = RoomHistoryService(repository=repository)

        result = service.get_context_by_ticket_key("T-00088")

        self.assertEqual(result, context)
        self.assertEqual(repository.calls[0]["method"], "get_by_ticket_key")

    def test_list_recent_tickets_for_location_excludes_current_ticket(self) -> None:
        now = datetime.now(timezone.utc)
        repository = FakeRoomHistoryRepository(
            items=[
                RoomTicketHistoryItem(
                    ticket_key="T-00090",
                    hotel_id=1,
                    location_id=12,
                    category_snapshot="Интернет",
                    status="закрыто",
                    created_at=now - timedelta(days=1),
                ),
                RoomTicketHistoryItem(
                    ticket_key="T-00091",
                    hotel_id=1,
                    location_id=12,
                    category_snapshot="ТВ",
                    status="в работе",
                    created_at=now - timedelta(days=2),
                ),
            ]
        )
        service = RoomHistoryService(repository=repository)

        items = service.list_recent_tickets_for_location(
            1,
            12,
            exclude_ticket_key="T-00090",
        )

        self.assertEqual([item.ticket_key for item in items], ["T-00091"])
        self.assertEqual(repository.calls[0]["exclude_ticket_key"], "T-00090")

    def test_list_recent_tickets_for_location_filters_other_location_and_hotel(self) -> None:
        now = datetime.now(timezone.utc)
        repository = FakeRoomHistoryRepository(
            items=[
                RoomTicketHistoryItem(
                    ticket_key="T-00090",
                    hotel_id=1,
                    location_id=12,
                    category_snapshot="Интернет",
                    status="закрыто",
                    created_at=now - timedelta(days=1),
                ),
                RoomTicketHistoryItem(
                    ticket_key="T-00091",
                    hotel_id=1,
                    location_id=99,
                    category_snapshot="ТВ",
                    status="закрыто",
                    created_at=now - timedelta(days=1),
                ),
                RoomTicketHistoryItem(
                    ticket_key="T-00092",
                    hotel_id=2,
                    location_id=12,
                    category_snapshot="Замок",
                    status="закрыто",
                    created_at=now - timedelta(days=1),
                ),
                RoomTicketHistoryItem(
                    ticket_key="T-00093",
                    hotel_id=1,
                    location_id=12,
                    category_snapshot="Прочее",
                    status="закрыто",
                    created_at=now - timedelta(days=400),
                ),
            ]
        )
        service = RoomHistoryService(repository=repository)

        items = service.list_recent_tickets_for_location(1, 12)

        self.assertEqual([item.ticket_key for item in items], ["T-00090", "T-00093"])

    def test_list_recent_tickets_for_location_respects_limit(self) -> None:
        now = datetime.now(timezone.utc)
        repository = FakeRoomHistoryRepository(
            items=[
                RoomTicketHistoryItem(
                    ticket_key=f"T-{index:05d}",
                    hotel_id=1,
                    location_id=12,
                    category_snapshot="ТВ",
                    status="закрыто",
                    created_at=now - timedelta(minutes=index),
                )
                for index in range(ROOM_HISTORY_LIMIT + 5)
            ]
        )
        service = RoomHistoryService(repository=repository)

        items = service.list_recent_tickets_for_location(
            1,
            12,
            limit=ROOM_HISTORY_LIMIT,
        )

        self.assertEqual(len(items), ROOM_HISTORY_LIMIT)
        self.assertEqual(repository.calls[0]["limit"], ROOM_HISTORY_LIMIT)

    def test_service_without_repository_returns_safe_defaults(self) -> None:
        service = RoomHistoryService()

        self.assertIsNone(service.get_context_by_ticket_key("T-00088"))
        self.assertEqual(service.list_recent_tickets_for_location(1, 12), [])


if __name__ == "__main__":
    unittest.main()
