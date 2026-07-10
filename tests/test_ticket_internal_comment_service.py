"""Проверки внутренних комментариев специалистов."""

import unittest
from datetime import datetime, timezone

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.repositories.ticket_context_repository import TicketCommentRecord
from app.helpdesk.services.ticket_internal_comment_service import (
    INTERNAL_COMMENT_DIRECTION,
    TicketInternalCommentService,
)


class FakeTicketContextRepository:
    """Минимальное хранилище записей комментариев для unit-тестов."""

    def __init__(self) -> None:
        self.saved: list[dict] = []

    def save_comment(self, **kwargs):
        self.saved.append(kwargs)
        return TicketCommentRecord(
            id=len(self.saved),
            ticket_id=kwargs["ticket_id"],
            direction=kwargs["direction"],
            body=kwargs["body"],
            created_at=datetime.now(timezone.utc),
            meta=kwargs["meta"],
        )

    def get_last_comment(self, *, ticket_id: str, direction: str, **kwargs):
        for item in reversed(self.saved):
            if item["ticket_id"] == ticket_id and item["direction"] == direction:
                return TicketCommentRecord(
                    id=1,
                    ticket_id=ticket_id,
                    direction=direction,
                    body=item["body"],
                    created_at=datetime.now(timezone.utc),
                    meta=item["meta"],
                )
        return None


class TicketInternalCommentServiceTests(unittest.TestCase):
    def test_saves_internal_comment_with_room_context_metadata(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketInternalCommentService(repository)
        ticket = Ticket(id="T-00103", user_id=10, category="Интернет", text="Нет сети")
        context = RoomTicketContext(
            ticket_key="T-00103",
            hotel_id=1,
            location_id=112,
            room_number_snapshot="112",
            category_snapshot="Интернет",
            issue_category_id=5,
        )

        service.save(
            ticket=ticket,
            actor_user_id=99,
            actor_name="Дмитрий",
            text="Проверить повторно.",
            room_context=context,
        )

        saved = repository.saved[0]
        self.assertEqual(saved["direction"], INTERNAL_COMMENT_DIRECTION)
        self.assertFalse(saved["meta"]["visible_to_user"])
        self.assertFalse(saved["meta"]["added_to_knowledge_base"])
        self.assertEqual(saved["meta"]["location_id"], 112)
        self.assertEqual(saved["meta"]["category_title"], "Интернет")
        self.assertEqual(saved["meta"]["source"], "ticket_internal_comment")

    def test_saves_comment_without_location_for_regular_ticket(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketInternalCommentService(repository)
        ticket = Ticket(id="T-00104", user_id=10, category="Прочее", text="Проверка")

        service.save(
            ticket=ticket,
            actor_user_id=99,
            actor_name="Дмитрий",
            text="Внутренний текст",
            room_context=None,
        )

        self.assertIsNone(repository.saved[0]["meta"]["location_id"])
        self.assertEqual(repository.saved[0]["meta"]["category_title"], "Прочее")

    def test_last_comment_preview_is_truncated(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketInternalCommentService(repository)
        ticket = Ticket(id="T-00105", user_id=10, category="ТВ", text="Проверка")
        service.save(
            ticket=ticket,
            actor_user_id=99,
            actor_name="Дмитрий",
            text="x" * 220,
            room_context=None,
        )

        comment = service.get_last("T-00105")

        self.assertIsNotNone(comment)
        self.assertEqual(len(comment.card_text), 180)
        self.assertTrue(comment.card_text.endswith("…"))


if __name__ == "__main__":
    unittest.main()
