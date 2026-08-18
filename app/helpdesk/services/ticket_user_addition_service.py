"""Сохранение пользовательских дополнений к существующим заявкам."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.helpdesk.repositories.ticket_context_repository import (
    TicketCommentRecord,
    TicketContextRepository,
)
from app.helpdesk.services.ticket_clarification_service import (
    build_ticket_attachment_metadata,
    restore_ticket_attachment,
)


logger = logging.getLogger(__name__)

COMMENT_USER_ADDITION = "user_addition"
ATTACHMENT_SOURCE_USER_ADDITION = "user_addition"
CARD_ADDITION_PREVIEW_LENGTH = 180


@dataclass(slots=True)
class TicketUserAddition:
    """Дополнение пользователя, сохранённое в истории заявки."""

    comment_id: int
    ticket_id: str
    user_id: int
    user_name: str
    text: str
    created_at: datetime
    attached_to_card: bool = False
    group_message_id: str | None = None
    attachments: list[Any] | None = None

    @property
    def card_text(self) -> str:
        text = self.text.strip() or "Без текста"
        if len(text) <= CARD_ADDITION_PREVIEW_LENGTH:
            return text
        return f"{text[:CARD_ADDITION_PREVIEW_LENGTH].rstrip()}..."


class TicketUserAdditionService:
    """Пишет дополнения и управляет их прикреплением к основной карточке."""

    def __init__(self, repository: TicketContextRepository | None = None) -> None:
        self._repository = repository
        self._memory: dict[int, TicketUserAddition] = {}
        self._counter = 0

    def save(
        self,
        *,
        ticket_id: str,
        user_id: int,
        user_name: str,
        text: str,
        attachments: list[Any] | None = None,
        source_message_id: str | None = None,
    ) -> TicketUserAddition:
        meta = {
            "source": "user_addition",
            "attached_to_card": False,
            "visible_to_user": True,
        }
        if self._repository is None:
            self._counter += 1
            item = TicketUserAddition(
                comment_id=self._counter,
                ticket_id=ticket_id,
                user_id=user_id,
                user_name=user_name,
                text=text,
                created_at=datetime.now(tz=timezone.utc),
                attachments=list(attachments or []),
            )
            self._memory[item.comment_id] = item
            return item
        comment = self._repository.save_comment(
            ticket_id=ticket_id,
            direction=COMMENT_USER_ADDITION,
            body=text,
            author_user_id=user_id,
            author_name=user_name,
            author_role="user",
            source_message_id=source_message_id,
            meta=meta,
        )
        for index, attachment in enumerate(attachments or []):
            metadata = build_ticket_attachment_metadata(
                attachment,
                source=ATTACHMENT_SOURCE_USER_ADDITION,
                order=index,
                source_message_id=source_message_id,
            )
            self._repository.save_attachment(
                ticket_id=ticket_id,
                comment_id=comment.id,
                platform_attachment_type=metadata.get("type"),
                platform_attachment_ref=metadata.get("token"),
                meta=metadata,
            )
        return self._from_comment(comment)

    def bind_group_message(self, comment_id: int, group_message_id: str) -> None:
        item = self.get(comment_id)
        if item is None:
            return
        if self._repository is not None:
            comment = self._repository.bind_comment_target_message(
                comment_id,
                str(group_message_id),
            )
            if comment is not None:
                item = self._from_comment(comment)
        item.group_message_id = str(group_message_id)
        self._memory[comment_id] = item

    def get(self, comment_id: int) -> TicketUserAddition | None:
        cached = self._memory.get(comment_id)
        if cached is not None:
            return cached
        if self._repository is None:
            return None
        comment = self._repository.get_comment(comment_id)
        if comment is None or comment.direction != COMMENT_USER_ADDITION:
            return None
        item = self._from_comment(comment)
        self._memory[item.comment_id] = item
        return item

    def attach(self, comment_id: int) -> TicketUserAddition | None:
        item = self.get(comment_id)
        if item is None:
            return None
        if item.attached_to_card:
            return item
        if self._repository is not None:
            comment = self._repository.mark_comment_attached(
                comment_id,
                direction=COMMENT_USER_ADDITION,
            )
            if comment is None:
                return None
            item = self._from_comment(comment)
        else:
            item.attached_to_card = True
        self._memory[comment_id] = item
        return item

    def get_last_attached(self, ticket_id: str) -> TicketUserAddition | None:
        if self._repository is not None:
            comment = self._repository.get_last_comment(
                ticket_id=ticket_id,
                direction=COMMENT_USER_ADDITION,
                attached_to_card=True,
            )
            return self._from_comment(comment) if comment else None
        items = [
            item for item in self._memory.values()
            if item.ticket_id == ticket_id and item.attached_to_card
        ]
        return max(items, key=lambda item: item.created_at) if items else None

    def get_last(self, ticket_id: str) -> TicketUserAddition | None:
        """Возвращает последнее дополнение для личной карточки пользователя."""

        if self._repository is not None:
            comment = self._repository.get_last_comment(
                ticket_id=ticket_id,
                direction=COMMENT_USER_ADDITION,
            )
            return self._from_comment(comment) if comment else None
        items = [item for item in self._memory.values() if item.ticket_id == ticket_id]
        return max(items, key=lambda item: item.created_at) if items else None

    def _from_comment(self, comment: TicketCommentRecord) -> TicketUserAddition:
        attachments: list[Any] = []
        if self._repository is not None:
            records = self._repository.list_attachments(
                ticket_id=comment.ticket_id,
                comment_id=comment.id,
            )
            attachments = [
                restored
                for record in records
                if (restored := restore_ticket_attachment(record)) is not None
            ]
        return TicketUserAddition(
            comment_id=comment.id,
            ticket_id=comment.ticket_id,
            user_id=comment.author_user_id or 0,
            user_name=comment.author_name or "Пользователь",
            text=comment.body,
            created_at=comment.created_at,
            attached_to_card=bool(comment.meta.get("attached_to_card")),
            group_message_id=comment.target_message_id,
            attachments=attachments,
        )
