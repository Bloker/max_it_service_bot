from datetime import datetime
import unittest

from app.helpdesk.models.knowledge_base import KnowledgeArticle, KnowledgeScope, KnowledgeScopeType
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.repositories.location_repository import HotelRef
from app.helpdesk.repositories.ticket_context_repository import TicketCommentRecord
from app.helpdesk.services.knowledge_base_service import KnowledgeBaseService
from app.helpdesk.services.location_service import LocationService


class KnowledgeBaseServiceTests(unittest.TestCase):
    def test_resolve_hotel_uses_user_membership_when_present(self) -> None:
        repository = _FakeLocationRepository(
            default_hotel=HotelRef(id=2, code="other", name="Other"),
            fallback_hotel=HotelRef(id=1, code="jamaica", name="Jamaica"),
        )
        service = KnowledgeBaseService(locations=LocationService(repository))

        hotel = service.resolve_hotel(101)

        self.assertEqual(hotel.code, "other")

    def test_resolve_hotel_falls_back_to_jamaica_when_membership_missing(self) -> None:
        repository = _FakeLocationRepository(
            default_hotel=None,
            fallback_hotel=HotelRef(id=1, code="jamaica", name="Jamaica"),
        )
        service = KnowledgeBaseService(locations=LocationService(repository))

        hotel = service.resolve_hotel(101)

        self.assertIsNotNone(hotel)
        self.assertEqual(hotel.code, "jamaica")
        self.assertEqual(repository.last_hotel_code_lookup, "jamaica")

    def test_article_model_uses_active_flag_without_legacy_fields(self) -> None:
        article = _article_from_payload(_ArticlePayload())

        self.assertTrue(article.is_active)
        self.assertFalse(hasattr(article, "status"))
        self.assertFalse(hasattr(article, "visibility"))
        self.assertFalse(hasattr(article, "published_at"))

    def test_create_manual_article_creates_active_article(self) -> None:
        kb_repository = _FakeKnowledgeRepository()
        service = KnowledgeBaseService(repository=kb_repository)

        article = service.create_manual_article(
            scope_id=1,
            hotel_id=2,
            category_id=3,
            title="Нет сигнала",
            body="Проверить питание.",
            author_user_id=10,
        )

        self.assertTrue(article.is_active)
        self.assertIsNone(article.source_ticket_key)

    def test_category_list_uses_simple_active_repository_query(self) -> None:
        kb_repository = _FakeKnowledgeRepository()
        service = KnowledgeBaseService(repository=kb_repository)

        service.list_articles_for_category(scope_id=1, category_id=3)

        self.assertEqual(kb_repository.list_call, {"scope_id": 1, "category_id": 3, "limit": 10})

    def test_ticket_note_creates_article_and_comment_metadata_without_link_table(self) -> None:
        kb_repository = _FakeKnowledgeRepository()
        ticket_contexts = _FakeTicketContexts()
        service = KnowledgeBaseService(repository=kb_repository, ticket_contexts=ticket_contexts)
        ticket = Ticket(id="T-00101", user_id=100, category="ТВ", text="Не работает ТВ")
        room_context = RoomTicketContext(
            ticket_key=ticket.ticket_id,
            hotel_id=2,
            location_id=12,
            issue_category_id=3,
        )

        _, article = service.save_ticket_note(
            ticket=ticket,
            actor_user_id=10,
            actor_name="Дмитрий",
            title="Приставка висит на запуске",
            text="Нужно перепрошить приставку",
            room_context=room_context,
        )

        self.assertIsNotNone(article)
        self.assertEqual(article.source_ticket_key, "T-00101")
        self.assertEqual(article.source_location_id, 12)
        self.assertEqual(ticket_contexts.saved_meta["knowledge_article_id"], article.id)
        self.assertEqual(ticket_contexts.saved_meta["knowledge_title"], article.title)
        self.assertEqual(ticket_contexts.saved_meta["source"], "ticket_note")
        self.assertFalse(hasattr(kb_repository, "create_ticket_link"))

    def test_ticket_note_propagates_knowledge_article_save_failure(self) -> None:
        service = KnowledgeBaseService(repository=_FailingKnowledgeRepository())
        ticket = Ticket(id="T-00102", user_id=100, category="ТВ", text="Не работает ТВ")
        room_context = RoomTicketContext(
            ticket_key=ticket.ticket_id,
            hotel_id=2,
            location_id=12,
            issue_category_id=3,
        )

        with self.assertRaisesRegex(RuntimeError, "knowledge write failed"):
            service.save_ticket_note(
                ticket=ticket,
                actor_user_id=10,
                actor_name="Дмитрий",
                title="Нет сигнала",
                text="Проверить питание.",
                room_context=room_context,
            )


class _FakeLocationRepository:
    def __init__(self, *, default_hotel, fallback_hotel) -> None:
        self.default_hotel = default_hotel
        self.fallback_hotel = fallback_hotel
        self.last_hotel_code_lookup = None

    def find_hotel_by_code(self, code: str):
        self.last_hotel_code_lookup = code
        return self.fallback_hotel

    def find_user_default_hotel(self, user_id: int):
        return self.default_hotel

    def find_location_by_room_number(self, hotel_id: int, room_number: str):
        return None

    def list_issue_categories_for_hotel(self, hotel_id: int, *, requires_location=None):
        return ()


class _ArticlePayload:
    scope_id = 1
    hotel_id = 2
    category_id = 3
    title = "Тема"
    body = "Текст"
    source_ticket_key = None
    source_location_id = None
    author_user_id = 10
    is_active = True
    sort_order = 0
    metadata = {}


def _article_from_payload(payload, article_id: int = 1) -> KnowledgeArticle:
    return KnowledgeArticle(
        id=article_id,
        scope_id=payload.scope_id,
        hotel_id=payload.hotel_id,
        category_id=payload.category_id,
        title=payload.title,
        body=payload.body,
        source_ticket_key=payload.source_ticket_key,
        source_location_id=payload.source_location_id,
        author_user_id=payload.author_user_id,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
        metadata=payload.metadata,
    )


class _FakeKnowledgeRepository:
    def __init__(self) -> None:
        self._next_id = 1
        self.list_call = None

    def create_article(self, payload):
        article = _article_from_payload(payload, self._next_id)
        self._next_id += 1
        return article

    def list_scopes(self):
        return [
            KnowledgeScope(
                id=1,
                code="jamaica",
                title="Джамайка",
                scope_type=KnowledgeScopeType.HOTEL,
                hotel_id=2,
            )
        ]

    def list_articles(self, *, scope_id, category_id, limit):
        self.list_call = {
            "scope_id": scope_id,
            "category_id": category_id,
            "limit": limit,
        }
        return []


class _FailingKnowledgeRepository(_FakeKnowledgeRepository):
    def create_article(self, payload):
        raise RuntimeError("knowledge write failed")


class _FakeTicketContexts:
    def __init__(self) -> None:
        self.saved_meta = {}

    def save_comment(self, **kwargs):
        self.saved_meta = dict(kwargs["meta"])
        return TicketCommentRecord(
            id=1,
            ticket_id=kwargs["ticket_id"],
            direction=kwargs["direction"],
            body=kwargs["body"],
            created_at=datetime.now(),
            author_user_id=kwargs["author_user_id"],
            author_name=kwargs["author_name"],
            meta=self.saved_meta,
        )


if __name__ == "__main__":
    unittest.main()
