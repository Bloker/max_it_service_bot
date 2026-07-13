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
        self.assertEqual(session.location_id, 4)
        self.assertEqual(session.category_id, 3)
        service.finish(10)
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
