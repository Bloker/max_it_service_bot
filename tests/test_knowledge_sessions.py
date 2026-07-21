import unittest

from app.helpdesk.services.knowledge_article_create_session_service import (
    KnowledgeArticleCreateSessionService,
)
from app.helpdesk.services.ticket_internal_comment_session_service import (
    TicketInternalCommentSessionService,
)


class KnowledgeSessionsTests(unittest.TestCase):
    def test_internal_comment_session_round_trip(self) -> None:
        service = TicketInternalCommentSessionService()

        session = service.start(
            actor_user_id=10,
            actor_name="Дмитрий",
            ticket_id="T-00100",
            hotel_id=2,
            category_id=3,
            location_id=4,
            location_display="Номер 115 (Телефония)",
        )

        self.assertEqual(service.get(10), session)
        self.assertEqual(service.get_by_ticket("T-00100"), session)
        self.assertEqual(service.get_for_actor_ticket(10, "T-00100"), session)
        self.assertIsNone(service.get_for_actor_ticket(11, "T-00100"))
        self.assertIsNone(service.get_for_actor_ticket(10, "T-00999"))
        self.assertEqual(session.location_id, 4)
        self.assertEqual(session.category_id, 3)
        service.finish(10)
        self.assertIsNone(service.get(10))

    def test_internal_comment_sessions_are_resolved_by_actor_and_ticket(self) -> None:
        service = TicketInternalCommentSessionService()
        first = service.start(
            actor_user_id=10,
            actor_name="Первый",
            ticket_id="T-00100",
        )
        second = service.start(
            actor_user_id=20,
            actor_name="Второй",
            ticket_id="T-00200",
        )

        self.assertEqual(service.get_for_actor_ticket(10, "T-00100"), first)
        self.assertEqual(service.get_for_actor_ticket(20, "T-00200"), second)
        self.assertIsNone(service.get_for_actor_ticket(10, "T-00200"))
        self.assertEqual(service.get(10), first)

    def test_internal_comment_cancel_requires_matching_actor_and_ticket(self) -> None:
        service = TicketInternalCommentSessionService()
        session = service.start(
            actor_user_id=10,
            actor_name="Первый",
            ticket_id="T-00100",
        )

        self.assertIsNone(service.cancel_for_actor_ticket(20, "T-00100"))
        self.assertIsNone(service.cancel_for_actor_ticket(10, "T-00999"))
        self.assertEqual(service.get(10), session)
        self.assertEqual(
            service.cancel_for_actor_ticket(10, "T-00100"),
            session,
        )
        self.assertIsNone(service.get(10))

    def test_article_create_session_steps(self) -> None:
        service = KnowledgeArticleCreateSessionService()

        session = service.start(actor_user_id=10, chat_id=100)
        self.assertEqual(session.step, "waiting_scope")

        session = service.set_scope(
            10,
            scope_id=1,
            scope_code="jamaica",
            scope_title="Джамайка",
            hotel_id=1,
        )
        self.assertEqual(session.step, "waiting_category")

        session = service.set_category(
            10,
            category_id=3,
            category_code="internet",
            category_title="Интернет",
        )
        self.assertEqual(session.step, "waiting_title")

        session = service.set_title(10, "Нет интернета")
        self.assertEqual(session.step, "waiting_body")
        self.assertEqual(session.title, "Нет интернета")

    def test_article_create_session_supports_ticket_note_mode(self) -> None:
        service = KnowledgeArticleCreateSessionService()

        session = service.start(
            actor_user_id=10,
            chat_id=-100,
            hotel_id=1,
            scope_id=2,
            scope_code="jamaica",
            scope_title="Джамайка",
            category_id=3,
            category_code="tv",
            category_title="ТВ",
            ticket_id="T-00104",
            source_kind="ticket_note",
        )

        self.assertEqual(session.step, "waiting_title")
        self.assertEqual(session.ticket_id, "T-00104")
        self.assertEqual(session.source_kind, "ticket_note")


if __name__ == "__main__":
    unittest.main()
