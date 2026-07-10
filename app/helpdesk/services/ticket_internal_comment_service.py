"""Сохранение и отображение внутренних комментариев специалистов."""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.repositories.ticket_context_repository import (
    TicketCommentRecord,
    TicketContextRepository,
)
from app.helpdesk.texts.formatters import format_room_context_object


logger = logging.getLogger(__name__)

INTERNAL_COMMENT_DIRECTION = "internal_comment"
MAX_INTERNAL_COMMENT_LENGTH = 4000
INTERNAL_COMMENT_PREVIEW_LENGTH = 180


@dataclass(frozen=True, slots=True)
class TicketInternalComment:
    """Последний внутренний комментарий для карточки заявки."""

    ticket_id: str
    body: str
    created_at: datetime | None = None

    @property
    def card_text(self) -> str:
        """Возвращает безопасный короткий preview для карточки."""

        compact = " ".join(self.body.strip().split())
        if len(compact) <= INTERNAL_COMMENT_PREVIEW_LENGTH:
            return compact
        return f"{compact[: INTERNAL_COMMENT_PREVIEW_LENGTH - 1].rstrip()}…"


class TicketInternalCommentService:
    """Работает только с внутренними записями `helpdesk.ticket_comments`."""

    def __init__(self, repository: TicketContextRepository | None = None) -> None:
        self._repository = repository

    def save(
        self,
        *,
        ticket: Ticket,
        actor_user_id: int,
        actor_name: str,
        text: str,
        room_context: RoomTicketContext | None,
        source_message_id: str | None = None,
        actor_role: str | None = None,
    ) -> TicketInternalComment:
        """Сохраняет комментарий без отправки пользователю и записи в БЗ."""

        body = text.strip()
        if not body:
            raise ValueError("Internal comment must not be empty")
        if len(body) > MAX_INTERNAL_COMMENT_LENGTH:
            raise ValueError("Internal comment is too long")

        location_display = self._location_display(room_context)
        meta = {
            "comment_type": "internal",
            "visible_to_user": False,
            "added_to_knowledge_base": False,
            "hotel_id": room_context.hotel_id if room_context else None,
            "location_id": room_context.location_id if room_context else None,
            "location_display": location_display,
            "category_id": room_context.issue_category_id if room_context else None,
            "category_title": (
                room_context.category_snapshot if room_context else ticket.category
            ),
            "source": "ticket_internal_comment",
        }
        if self._repository is None:
            return TicketInternalComment(ticket_id=ticket.ticket_id, body=body)

        record = self._repository.save_comment(
            ticket_id=ticket.ticket_id,
            direction=INTERNAL_COMMENT_DIRECTION,
            body=body,
            author_user_id=actor_user_id,
            author_name=actor_name,
            author_role=actor_role,
            source_message_id=source_message_id,
            meta=meta,
        )
        return self._from_record(record)

    def get_last(self, ticket_id: str) -> TicketInternalComment | None:
        """Возвращает последний внутренний комментарий заявки."""

        if self._repository is None:
            return None
        try:
            record = self._repository.get_last_comment(
                ticket_id=ticket_id,
                direction=INTERNAL_COMMENT_DIRECTION,
            )
        except Exception:
            logger.exception("Failed to read internal comment: ticket_id=%s", ticket_id)
            return None
        return self._from_record(record) if record is not None else None

    @staticmethod
    def _from_record(record: TicketCommentRecord) -> TicketInternalComment:
        """Преобразует запись репозитория в модель карточки."""

        return TicketInternalComment(
            ticket_id=record.ticket_id,
            body=record.body,
            created_at=record.created_at,
        )

    @staticmethod
    def _location_display(room_context: RoomTicketContext | None) -> str | None:
        """Собирает человекочитаемый объект для metadata комментария."""

        if room_context is None or room_context.location_id is None:
            return None
        return format_room_context_object(
            room_number_snapshot=room_context.room_number_snapshot,
            location_display_snapshot=room_context.location_display_snapshot,
            category_snapshot=None,
        )
