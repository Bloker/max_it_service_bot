"""Runtime и PostgreSQL-контекст уточнений/ответов по заявке."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload

from app.helpdesk.repositories.ticket_context_repository import (
    TicketAttachmentRecord,
    TicketCommentRecord,
    TicketContextRepository,
)
from app.helpdesk.services.attachment_filter_service import (
    get_attachment_token,
    is_audio_attachment,
)

logger = logging.getLogger(__name__)

MAX_CLARIFICATION_MESSAGE_LENGTH = 1000
CARD_CLARIFICATION_PREVIEW_LENGTH = 400

COMMENT_SPECIALIST_CLARIFICATION = "specialist_clarification"
COMMENT_USER_REPLY = "user_reply"
COMMENT_CLOSING_REPLY = "closing_reply"
ATTACHMENT_SOURCE_TICKET_INITIAL = "ticket_initial"
ATTACHMENT_SOURCE_SPECIALIST_CLARIFICATION = "specialist_clarification"
ATTACHMENT_SOURCE_USER_REPLY = "user_reply"
ATTACHMENT_SOURCE_CLOSING_REPLY = "closing_reply"


@dataclass(slots=True)
class TicketClarification:
    """Последнее уточнение для карточки заявки."""

    ticket_id: str
    actor_user_id: int
    actor_name: str
    text: str
    created_at: datetime
    attachments: list[Any] | None = None

    @property
    def card_text(self) -> str:
        """Возвращает короткий текст для карточки заявки."""

        if len(self.text) <= CARD_CLARIFICATION_PREVIEW_LENGTH:
            return self.text
        return f"{self.text[:CARD_CLARIFICATION_PREVIEW_LENGTH].rstrip()}..."


@dataclass(slots=True)
class TicketUserReply:
    """Ответ пользователя, который можно показать в карточке."""

    ticket_id: str
    user_id: int
    user_name: str
    text: str
    created_at: datetime
    group_message_id: str | None = None
    attachments: list[Any] | None = None

    @property
    def card_text(self) -> str:
        """Возвращает короткий текст для карточки заявки."""

        if len(self.text) <= CARD_CLARIFICATION_PREVIEW_LENGTH:
            return self.text
        return f"{self.text[:CARD_CLARIFICATION_PREVIEW_LENGTH].rstrip()}..."


@dataclass(slots=True)
class TicketClosingReply:
    """Ответ специалиста при закрытии заявки."""

    ticket_id: str
    actor_user_id: int
    actor_name: str
    text: str
    created_at: datetime
    source_message_id: str | None = None
    target_message_id: str | None = None
    attachments: list[Any] | None = None

    @property
    def card_text(self) -> str:
        """Возвращает короткий текст для карточки заявки."""

        if len(self.text) <= CARD_CLARIFICATION_PREVIEW_LENGTH:
            return self.text
        return f"{self.text[:CARD_CLARIFICATION_PREVIEW_LENGTH].rstrip()}..."


class TicketClarificationService:
    """Хранит последние уточнения в runtime и, если доступно, в PostgreSQL."""

    def __init__(self, repository: TicketContextRepository | None = None) -> None:
        self._repository = repository
        self._items: dict[str, TicketClarification] = {}
        self._attached_user_replies: dict[str, TicketUserReply] = {}
        self._user_replies_by_group_mid: dict[str, TicketUserReply] = {}
        self._ticket_base_attachments: dict[str, list[Any]] = {}
        self._closing_replies: dict[str, TicketClosingReply] = {}

    def save_last(
        self,
        *,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any] | None = None,
        source_message_id: str | None = None,
        target_message_id: str | None = None,
    ) -> TicketClarification:
        """Сохраняет последнее уточнение заявки."""

        item = TicketClarification(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            text=text,
            created_at=datetime.now(tz=timezone.utc),
            attachments=list(attachments or []),
        )
        self._items[ticket_id] = item
        comment = self._save_comment_safely(
            ticket_id=ticket_id,
            direction=COMMENT_SPECIALIST_CLARIFICATION,
            body=text,
            author_user_id=actor_user_id,
            author_name=actor_name,
            author_role="IT specialist",
            source_message_id=source_message_id,
            target_message_id=target_message_id,
            meta={"attached_to_card": True},
        )
        self._save_attachments_safely(
            ticket_id=ticket_id,
            attachments=attachments,
            source=ATTACHMENT_SOURCE_SPECIALIST_CLARIFICATION,
            comment_id=comment.id if comment else None,
            source_message_id=source_message_id,
        )
        return item

    def get_last(self, ticket_id: str) -> TicketClarification | None:
        """Возвращает последнее уточнение по заявке."""

        cached = self._items.get(ticket_id)
        if cached is not None:
            return cached
        comment = self._get_last_comment_safely(
            ticket_id=ticket_id,
            direction=COMMENT_SPECIALIST_CLARIFICATION,
        )
        if comment is None:
            return None
        item = self._clarification_from_comment(comment)
        self._items[ticket_id] = item
        return item

    def set_ticket_base_attachments(
        self,
        *,
        ticket_id: str,
        attachments: list[Any] | None,
    ) -> None:
        """Сохраняет исходные вложения карточки заявки."""

        normalized = list(attachments or [])
        self._ticket_base_attachments[ticket_id] = normalized
        self._save_attachments_safely(
            ticket_id=ticket_id,
            attachments=normalized,
            source=ATTACHMENT_SOURCE_TICKET_INITIAL,
        )

    def get_ticket_base_attachments(self, ticket_id: str) -> list[Any]:
        """Возвращает исходные вложения карточки заявки."""

        cached = self._ticket_base_attachments.get(ticket_id)
        if cached is not None:
            return list(cached)
        restored = self._restore_attachments_safely(
            ticket_id=ticket_id,
            source=ATTACHMENT_SOURCE_TICKET_INITIAL,
        )
        if restored:
            self._ticket_base_attachments[ticket_id] = restored
        return restored

    def save_user_reply_candidate(
        self,
        *,
        ticket_id: str,
        user_id: int,
        user_name: str,
        text: str,
        group_message_id: str,
        attachments: list[Any] | None = None,
        source_message_id: str | None = None,
    ) -> TicketUserReply:
        """Сохраняет ответ пользователя до прикрепления к карточке."""

        item = TicketUserReply(
            ticket_id=ticket_id,
            user_id=user_id,
            user_name=user_name,
            text=text,
            created_at=datetime.now(tz=timezone.utc),
            group_message_id=str(group_message_id),
            attachments=list(attachments or []),
        )
        self._user_replies_by_group_mid[str(group_message_id)] = item
        comment = self._save_comment_safely(
            ticket_id=ticket_id,
            direction=COMMENT_USER_REPLY,
            body=text,
            author_user_id=user_id,
            author_name=user_name,
            author_role="user",
            source_message_id=source_message_id,
            target_message_id=str(group_message_id),
            meta={"attached_to_card": False},
        )
        self._save_attachments_safely(
            ticket_id=ticket_id,
            attachments=attachments,
            source=ATTACHMENT_SOURCE_USER_REPLY,
            comment_id=comment.id if comment else None,
            source_message_id=source_message_id,
        )
        return item

    def get_user_reply_by_group_message(
        self,
        group_message_id: str,
    ) -> TicketUserReply | None:
        """Возвращает ответ пользователя по сообщению в группе."""

        cached = self._user_replies_by_group_mid.get(str(group_message_id))
        if cached is not None:
            return cached
        if self._repository is None:
            return None
        try:
            comment = self._repository.get_user_reply_by_group_message(str(group_message_id))
        except Exception:
            logger.warning(
                "Failed to restore user reply by group message: group_message_id=%s",
                group_message_id,
                exc_info=True,
            )
            return None
        if comment is None:
            return None
        item = self._user_reply_from_comment(comment)
        self._user_replies_by_group_mid[str(group_message_id)] = item
        return item

    def attach_user_reply(self, group_message_id: str) -> TicketUserReply | None:
        """Прикрепляет ответ пользователя к карточке заявки."""

        item = self.get_user_reply_by_group_message(group_message_id)
        if item is None:
            return None
        if self._repository is not None:
            try:
                comment = self._repository.mark_user_reply_attached(str(group_message_id))
                if comment is not None:
                    item = self._user_reply_from_comment(comment)
            except Exception:
                logger.warning(
                    "Failed to persist attached user reply: group_message_id=%s",
                    group_message_id,
                    exc_info=True,
                )
        self._attached_user_replies[item.ticket_id] = item
        return item

    def get_attached_user_reply(self, ticket_id: str) -> TicketUserReply | None:
        """Возвращает последний прикреплённый ответ пользователя."""

        cached = self._attached_user_replies.get(ticket_id)
        if cached is not None:
            return cached
        comment = self._get_last_comment_safely(
            ticket_id=ticket_id,
            direction=COMMENT_USER_REPLY,
            attached_to_card=True,
        )
        if comment is None:
            return None
        item = self._user_reply_from_comment(comment)
        self._attached_user_replies[ticket_id] = item
        if item.group_message_id:
            self._user_replies_by_group_mid[item.group_message_id] = item
        return item

    def save_closing_reply(
        self,
        *,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any] | None = None,
        source_message_id: str | None = None,
        target_message_id: str | None = None,
        actor_role: str = "IT specialist",
    ) -> TicketClosingReply:
        """Сохраняет ответ специалиста при закрытии заявки."""

        item = TicketClosingReply(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            text=text,
            created_at=datetime.now(tz=timezone.utc),
            source_message_id=source_message_id,
            target_message_id=target_message_id,
            attachments=list(attachments or []),
        )
        self._closing_replies[ticket_id] = item
        comment = self._save_comment_safely(
            ticket_id=ticket_id,
            direction=COMMENT_CLOSING_REPLY,
            body=text,
            author_user_id=actor_user_id,
            author_name=actor_name,
            author_role=actor_role,
            source_message_id=source_message_id,
            target_message_id=target_message_id,
            meta={"closed_with_reply": True, "attached_to_card": True},
        )
        self._save_attachments_safely(
            ticket_id=ticket_id,
            attachments=attachments,
            source=ATTACHMENT_SOURCE_CLOSING_REPLY,
            comment_id=comment.id if comment else None,
            source_message_id=source_message_id,
        )
        return item

    def get_closing_reply(self, ticket_id: str) -> TicketClosingReply | None:
        """Возвращает последний ответ при закрытии заявки."""

        cached = self._closing_replies.get(ticket_id)
        if cached is not None:
            return cached
        comment = self._get_last_comment_safely(
            ticket_id=ticket_id,
            direction=COMMENT_CLOSING_REPLY,
            attached_to_card=True,
        )
        if comment is None:
            return None
        item = self._closing_reply_from_comment(comment)
        self._closing_replies[ticket_id] = item
        return item

    def _save_comment_safely(self, **kwargs) -> TicketCommentRecord | None:
        """Пишет комментарий в БД, не ломая runtime-сценарий при ошибке."""

        if self._repository is None:
            return None
        try:
            return self._repository.save_comment(**kwargs)
        except Exception:
            logger.warning(
                "Failed to persist ticket comment: ticket_id=%s direction=%s",
                kwargs.get("ticket_id"),
                kwargs.get("direction"),
                exc_info=True,
            )
            return None

    def _save_attachments_safely(
        self,
        *,
        ticket_id: str,
        attachments: list[Any] | None,
        source: str,
        comment_id: int | None = None,
        source_message_id: str | None = None,
    ) -> None:
        """Сохраняет metadata вложений без приватных URL."""

        if self._repository is None or not attachments:
            return
        for index, attachment in enumerate(attachments):
            metadata = build_ticket_attachment_metadata(
                attachment,
                source=source,
                order=index,
                source_message_id=source_message_id,
            )
            try:
                self._repository.save_attachment(
                    ticket_id=ticket_id,
                    comment_id=comment_id,
                    platform_attachment_type=metadata.get("type"),
                    platform_attachment_ref=metadata.get("token"),
                    meta=metadata,
                )
            except Exception:
                logger.warning(
                    "Failed to persist ticket attachment metadata: ticket_id=%s source=%s",
                    ticket_id,
                    source,
                    exc_info=True,
                )

    def _restore_attachments_safely(
        self,
        *,
        ticket_id: str,
        source: str | None = None,
        comment_id: int | None = None,
    ) -> list[Any]:
        """Восстанавливает только attachments с сохранённым reusable token."""

        if self._repository is None:
            return []
        try:
            records = self._repository.list_attachments(
                ticket_id=ticket_id,
                source=source,
                comment_id=comment_id,
            )
        except Exception:
            logger.warning(
                "Failed to restore ticket attachment metadata: ticket_id=%s source=%s",
                ticket_id,
                source,
                exc_info=True,
            )
            return []
        restored: list[Any] = []
        for record in records:
            attachment = restore_ticket_attachment(record)
            if attachment is not None:
                restored.append(attachment)
        return restored

    def _get_last_comment_safely(
        self,
        *,
        ticket_id: str,
        direction: str,
        attached_to_card: bool | None = None,
    ) -> TicketCommentRecord | None:
        if self._repository is None:
            return None
        try:
            return self._repository.get_last_comment(
                ticket_id=ticket_id,
                direction=direction,
                attached_to_card=attached_to_card,
            )
        except Exception:
            logger.warning(
                "Failed to restore ticket comment: ticket_id=%s direction=%s",
                ticket_id,
                direction,
                exc_info=True,
            )
            return None

    def _clarification_from_comment(self, comment: TicketCommentRecord) -> TicketClarification:
        attachments = self._restore_attachments_safely(
            ticket_id=comment.ticket_id,
            comment_id=comment.id,
        )
        return TicketClarification(
            ticket_id=comment.ticket_id,
            actor_user_id=comment.author_user_id or 0,
            actor_name=comment.author_name or "Специалист",
            text=comment.body,
            created_at=comment.created_at,
            attachments=attachments,
        )

    def _user_reply_from_comment(self, comment: TicketCommentRecord) -> TicketUserReply:
        attachments = self._restore_attachments_safely(
            ticket_id=comment.ticket_id,
            comment_id=comment.id,
        )
        return TicketUserReply(
            ticket_id=comment.ticket_id,
            user_id=comment.author_user_id or 0,
            user_name=comment.author_name or "Пользователь",
            text=comment.body,
            created_at=comment.created_at,
            group_message_id=comment.target_message_id,
            attachments=attachments,
        )

    def _closing_reply_from_comment(self, comment: TicketCommentRecord) -> TicketClosingReply:
        return TicketClosingReply(
            ticket_id=comment.ticket_id,
            actor_user_id=comment.author_user_id or 0,
            actor_name=comment.author_name or "Специалист",
            text=comment.body,
            created_at=comment.created_at,
            source_message_id=comment.source_message_id,
            target_message_id=comment.target_message_id,
            attachments=self._restore_attachments_safely(
                ticket_id=comment.ticket_id,
                comment_id=comment.id,
            ),
        )


def build_ticket_attachment_metadata(
    attachment: Any,
    *,
    source: str,
    order: int,
    source_message_id: str | None = None,
) -> dict[str, Any]:
    """Извлекает безопасную metadata вложения без media URL."""

    attachment_type = _resolve_attachment_type(attachment)
    metadata: dict[str, Any] = {
        "source": source,
        "order": order,
        "type": attachment_type,
        "has_token": bool(get_attachment_token(attachment)),
        "is_audio": is_audio_attachment(attachment),
    }
    if source_message_id:
        metadata["source_message_id"] = str(source_message_id)
    token = get_attachment_token(attachment)
    if token:
        metadata["token"] = token
    for target_name, field_names in {
        "filename": ("filename", "file_name", "name"),
        "content_type": ("content_type", "mime_type", "media_type"),
        "size": ("size", "file_size"),
    }.items():
        value = _first_attachment_value(attachment, field_names)
        if value is not None:
            metadata[target_name] = value
    return metadata


def _resolve_attachment_type(attachment: Any) -> str:
    """Возвращает нормализованный тип вложения."""

    raw_type = str(getattr(attachment, "type", "") or "").lower()
    if is_audio_attachment(attachment):
        return "audio"
    if raw_type == "document":
        return "file"
    if raw_type == "photo":
        return "image"
    return raw_type or attachment.__class__.__name__.lower()


def _first_attachment_value(attachment: Any, field_names: tuple[str, ...]) -> Any:
    """Достаёт первое безопасное поле из attachment или payload."""

    payload = getattr(attachment, "payload", None)
    for field_name in field_names:
        value = getattr(attachment, field_name, None)
        if value is not None:
            return value
        if isinstance(payload, dict):
            value = payload.get(field_name)
        elif payload is not None:
            value = getattr(payload, field_name, None)
        if value is not None:
            return value
    return None


def restore_ticket_attachment(record: TicketAttachmentRecord) -> Any | None:
    """Восстанавливает AttachmentUpload, если есть reusable token."""

    token = record.platform_attachment_ref or record.meta.get("token")
    attachment_type = record.platform_attachment_type or record.meta.get("type")
    if not token or not attachment_type:
        return None
    try:
        upload_type = UploadType(str(attachment_type))
    except ValueError:
        return None
    return AttachmentUpload(
        type=upload_type,
        payload=AttachmentPayload(token=str(token)),
    )
