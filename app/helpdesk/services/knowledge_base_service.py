"""Сервисный слой MVP базы знаний HelpDesk."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.helpdesk.models.knowledge_base import (
    KnowledgeArticle,
    KnowledgeScope,
    KnowledgeScopeType,
)
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.repositories.knowledge_base_repository import (
    CreateKnowledgeArticleInput,
    KnowledgeBaseRepository,
)
from app.helpdesk.repositories.location_repository import HotelRef, IssueCategoryRef
from app.helpdesk.repositories.ticket_context_repository import TicketContextRepository
from app.helpdesk.services.location_service import LocationService

logger = logging.getLogger(__name__)

COMMENT_SPECIALIST_INTERNAL = "specialist_comment"
COMMENT_CARD_PREVIEW_LENGTH = 400


@dataclass(slots=True, frozen=True)
class TicketSpecialistComment:
    """Последняя заметка специалиста для карточки заявки."""

    ticket_id: str
    actor_user_id: int | None
    actor_name: str
    title: str
    text: str
    created_at: datetime

    @property
    def card_text(self) -> str:
        """Возвращает короткий текст заметки для карточки заявки."""

        first_line = self.text.splitlines()[0].strip()
        if len(first_line) <= COMMENT_CARD_PREVIEW_LENGTH:
            return first_line
        return f"{first_line[:COMMENT_CARD_PREVIEW_LENGTH].rstrip()}..."


class KnowledgeBaseService:
    """Координирует простые записи базы знаний и внутренние заметки."""

    def __init__(
        self,
        *,
        repository: KnowledgeBaseRepository | None = None,
        ticket_contexts: TicketContextRepository | None = None,
        locations: LocationService | None = None,
    ) -> None:
        self._repository = repository
        self._ticket_contexts = ticket_contexts
        self._locations = locations

    def is_available(self) -> bool:
        """Показывает, подключена ли persistent-база знаний."""

        return self._repository is not None and self._locations is not None

    def find_user_hotel(self, user_id: int) -> HotelRef | None:
        """Возвращает отель пользователя для KB-сценариев."""

        if self._locations is None:
            return None
        return self._locations.find_user_default_hotel(user_id)

    def resolve_hotel(
        self,
        user_id: int,
        *,
        fallback_code: str = "jamaica",
    ) -> HotelRef | None:
        """Возвращает отель пользователя или fallback-отель по коду."""

        hotel = self.find_user_hotel(user_id)
        if hotel is not None:
            return hotel
        if self._locations is None:
            return None
        return self._locations.find_hotel_by_code(fallback_code)

    def list_categories_for_hotel(self, hotel_id: int) -> tuple[IssueCategoryRef, ...]:
        """Возвращает доступные категории KB для отеля."""

        if self._locations is None:
            return ()
        return self._locations.list_issue_categories_for_hotel(hotel_id, requires_location=None)

    def list_scopes(self) -> list[KnowledgeScope]:
        """Возвращает активные разделы базы знаний."""

        if self._repository is None:
            return []
        return self._repository.list_scopes()

    def get_scope(self, scope_id: int) -> KnowledgeScope | None:
        """Возвращает раздел базы знаний по ID."""

        if self._repository is None:
            return None
        return self._repository.get_scope(scope_id)

    def get_scope_by_code(self, code: str) -> KnowledgeScope | None:
        """Возвращает раздел базы знаний по коду."""

        if self._repository is None:
            return None
        return self._repository.get_scope_by_code(code)

    def get_category_by_code(self, hotel_id: int, category_code: str) -> IssueCategoryRef | None:
        """Возвращает категорию отеля по коду."""

        normalized = (category_code or "").strip().lower()
        for category in self.list_categories_for_hotel(hotel_id):
            if category.code == normalized:
                return category
        return None

    def list_categories_for_scope(self, scope_id: int) -> tuple[IssueCategoryRef, ...]:
        """Возвращает категории для выбранного scope."""

        if self._repository is None:
            return ()
        return self._repository.list_categories_for_scope(scope_id)

    def get_category_by_id(self, scope_id: int, category_id: int) -> IssueCategoryRef | None:
        """Возвращает категорию scope по ID."""

        for category in self.list_categories_for_scope(scope_id):
            if category.id == category_id:
                return category
        return None

    def list_articles_for_category(
        self,
        *,
        scope_id: int,
        category_id: int,
        limit: int = 10,
    ) -> list[KnowledgeArticle]:
        """Возвращает статьи по категории для экрана KB."""

        if self._repository is None:
            return []
        return self._repository.list_articles(
            scope_id=scope_id,
            category_id=category_id,
            limit=limit,
        )

    def get_article(self, article_id: int) -> KnowledgeArticle | None:
        """Возвращает одну статью KB."""

        if self._repository is None:
            return None
        return self._repository.get_article(article_id)

    def create_manual_article(
        self,
        *,
        scope_id: int,
        hotel_id: int | None,
        category_id: int,
        title: str,
        body: str,
        author_user_id: int,
    ) -> KnowledgeArticle:
        """Создает активную ручную запись KB."""

        if self._repository is None:
            raise RuntimeError("Knowledge base repository is not configured")
        return self._repository.create_article(
            CreateKnowledgeArticleInput(
                scope_id=scope_id,
                hotel_id=hotel_id,
                category_id=category_id,
                title=title.strip(),
                body=body.strip(),
                author_user_id=author_user_id,
            )
        )

    def create_article_from_ticket_note(
        self,
        *,
        ticket_key: str,
        scope_id: int,
        hotel_id: int | None,
        category_id: int,
        title: str,
        body: str,
        source_location_id: int | None,
        author_user_id: int | None,
    ) -> KnowledgeArticle:
        """Создает активную KB-запись из заметки по заявке."""

        if self._repository is None:
            raise RuntimeError("Knowledge base repository is not configured")
        return self._repository.create_article(
            CreateKnowledgeArticleInput(
                scope_id=scope_id,
                hotel_id=hotel_id,
                category_id=category_id,
                title=title.strip(),
                body=body.strip(),
                source_ticket_key=ticket_key,
                source_location_id=source_location_id,
                author_user_id=author_user_id,
                metadata={"source": "ticket_note"},
            )
        )

    def save_ticket_note(
        self,
        *,
        ticket: Ticket,
        actor_user_id: int,
        actor_name: str,
        title: str,
        text: str,
        room_context: RoomTicketContext | None = None,
        source_message_id: str | None = None,
        actor_role: str = "IT specialist",
    ) -> tuple[TicketSpecialistComment, KnowledgeArticle | None]:
        """Сохраняет заметку специалиста и простую KB-запись."""

        normalized_title = title.strip()
        normalized_text = text.strip()
        if not normalized_title:
            raise ValueError("Comment title must not be empty")
        if not normalized_text:
            raise ValueError("Comment text must not be empty")

        preview = TicketSpecialistComment(
            ticket_id=ticket.ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            title=normalized_title,
            text=normalized_text,
            created_at=datetime.now(),
        )

        if self._repository is None:
            raise RuntimeError("Knowledge base repository is not configured")

        scope_id = self._resolve_scope_id_for_comment(room_context)
        category_id = room_context.issue_category_id if room_context else None
        if scope_id is None or category_id is None:
            raise RuntimeError("Ticket note requires room scope and category")

        # Статья БЗ - обязательный результат сценария [Заметка]. Не скрываем
        # ошибку записи, иначе карточка ошибочно сообщает об успешном сохранении.
        article = self.create_article_from_ticket_note(
            ticket_key=ticket.ticket_id,
            scope_id=scope_id,
            hotel_id=room_context.hotel_id if room_context else None,
            category_id=category_id,
            title=normalized_title,
            body=normalized_text,
            source_location_id=room_context.location_id if room_context else None,
            author_user_id=actor_user_id,
        )

        if self._ticket_contexts is not None:
            try:
                comment_record = self._ticket_contexts.save_comment(
                    ticket_id=ticket.ticket_id,
                    direction=COMMENT_SPECIALIST_INTERNAL,
                    body=normalized_text,
                    author_user_id=actor_user_id,
                    author_name=actor_name,
                    author_role=actor_role,
                    source_message_id=source_message_id,
                    meta={
                        "attached_to_card": True,
                        "knowledge_article_id": article.id if article else None,
                        "knowledge_title": normalized_title,
                        "added_to_knowledge_base": article is not None,
                        "source": "ticket_note",
                    },
                )
                preview = self._comment_from_record(comment_record)
            except Exception:
                logger.exception(
                    "Failed to save ticket note: "
                    "ticket_id=%s actor_user_id=%s",
                    ticket.ticket_id,
                    actor_user_id,
                )

        return preview, article

    def get_last_ticket_comment(self, ticket_id: str) -> TicketSpecialistComment | None:
        """Возвращает последний комментарий специалиста по заявке."""

        if self._ticket_contexts is None:
            return None
        try:
            record = self._ticket_contexts.get_last_comment(
                ticket_id=ticket_id,
                direction=COMMENT_SPECIALIST_INTERNAL,
            )
        except Exception:
            logger.exception(
                "Failed to read last specialist comment: ticket_id=%s",
                ticket_id,
            )
            return None
        if record is None:
            return None
        return self._comment_from_record(record)

    def resolve_scope_id_for_room_context(self, room_context: RoomTicketContext | None) -> int | None:
        """Возвращает scope_id для room-context заявки."""

        return self._resolve_scope_id_for_comment(room_context)

    def _resolve_scope_id_for_comment(self, room_context: RoomTicketContext | None) -> int | None:
        """Определяет scope для candidate-статьи из комментария заявки."""

        if self._repository is None or room_context is None or room_context.hotel_id is None:
            return None
        for scope in self._repository.list_scopes():
            if scope.scope_type == KnowledgeScopeType.HOTEL and scope.hotel_id == room_context.hotel_id:
                return scope.id
        return None

    def _comment_from_record(self, record) -> TicketSpecialistComment:
        return TicketSpecialistComment(
            ticket_id=record.ticket_id,
            actor_user_id=record.author_user_id,
            actor_name=record.author_name or "Специалист",
            title=str(record.meta.get("knowledge_title") or "Заметка"),
            text=record.body,
            created_at=record.created_at,
        )
