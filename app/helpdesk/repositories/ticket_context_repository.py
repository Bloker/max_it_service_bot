"""Контракты persistent-контекста карточки заявки."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class TicketCommentRecord:
    """Комментарий заявки, сохранённый в PostgreSQL."""

    id: int
    ticket_id: str
    direction: str
    body: str
    created_at: datetime
    author_user_id: int | None = None
    author_name: str | None = None
    author_role: str | None = None
    source_message_id: str | None = None
    target_message_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TicketAttachmentRecord:
    """Metadata вложения заявки без приватных media URL."""

    id: int
    ticket_id: str
    platform_attachment_type: str | None = None
    platform_attachment_ref: str | None = None
    comment_id: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class TicketContextRepository(Protocol):
    """Контракт постоянного хранения комментариев и вложений."""

    def save_comment(
        self,
        *,
        ticket_id: str,
        direction: str,
        body: str,
        author_user_id: int | None = None,
        author_name: str | None = None,
        author_role: str | None = None,
        source_message_id: str | None = None,
        target_message_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> TicketCommentRecord: ...

    def save_attachment(
        self,
        *,
        ticket_id: str,
        comment_id: int | None = None,
        platform_attachment_type: str | None = None,
        platform_attachment_ref: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> TicketAttachmentRecord: ...

    def list_attachments(
        self,
        *,
        ticket_id: str,
        source: str | None = None,
        comment_id: int | None = None,
    ) -> list[TicketAttachmentRecord]: ...

    def get_last_comment(
        self,
        *,
        ticket_id: str,
        direction: str,
        attached_to_card: bool | None = None,
    ) -> TicketCommentRecord | None: ...

    def get_user_reply_by_group_message(
        self,
        group_message_id: str,
    ) -> TicketCommentRecord | None: ...

    def mark_user_reply_attached(self, group_message_id: str) -> TicketCommentRecord | None: ...
