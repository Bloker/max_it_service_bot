"""SQLAlchemy models схемы helpdesk."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db.base import Base


class Ticket(Base):
    """Read-only reference на helpdesk.tickets для FK/lookup."""

    __tablename__ = "tickets"
    __table_args__ = (
        Index("idx_helpdesk_tickets_requester", "requester_user_id", "updated_at"),
        Index("idx_helpdesk_tickets_status", "status_code", "updated_at"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    requester_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requester_name: Mapped[str | None] = mapped_column(Text)
    requester_phone: Mapped[str | None] = mapped_column(Text)
    requester_department: Mapped[str | None] = mapped_column(Text)
    category_code: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_user_id: Mapped[int | None] = mapped_column(BigInteger)
    assignee_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketEvent(Base):
    """Business/technical event заявки."""

    __tablename__ = "ticket_events"
    __table_args__ = (
        Index("idx_helpdesk_ticket_events_ticket", "ticket_id", "created_at"),
        Index("idx_helpdesk_ticket_events_type", "event_type", "created_at"),
        Index("idx_helpdesk_ticket_events_actor", "actor_user_id", "created_at"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("helpdesk.tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    actor_name: Mapped[str | None] = mapped_column(Text)
    old_status_code: Mapped[str | None] = mapped_column(Text)
    new_status_code: Mapped[str | None] = mapped_column(Text)
    actor_role: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    related_message_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TicketComment(Base):
    """Комментарий или сообщение по заявке."""

    __tablename__ = "ticket_comments"
    __table_args__ = (
        Index("idx_helpdesk_ticket_comments_direction", "ticket_id", "direction", "created_at"),
        Index("idx_helpdesk_ticket_comments_target_mid", "target_message_id"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("helpdesk.tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[int | None] = mapped_column(BigInteger)
    author_name: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_role: Mapped[str | None] = mapped_column(Text)
    source_message_id: Mapped[str | None] = mapped_column(Text)
    target_message_id: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TicketAttachment(Base):
    """Metadata вложения заявки."""

    __tablename__ = "ticket_attachments"
    __table_args__ = (
        Index("idx_helpdesk_ticket_attachments_ticket", "ticket_id", "created_at"),
        Index("idx_helpdesk_ticket_attachments_comment", "comment_id"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("helpdesk.tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    comment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("helpdesk.ticket_comments.id", ondelete="CASCADE"),
    )
    platform_attachment_type: Mapped[str | None] = mapped_column(Text)
    platform_attachment_ref: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MediaAttachment(Base):
    """Media metadata комментариев и статей KB."""

    __tablename__ = "media_attachments"
    __table_args__ = (
        Index("idx_media_attachments_owner", "owner_type", "owner_id"),
        Index("idx_media_attachments_ticket", "ticket_key"),
        Index("idx_media_attachments_location", "hotel_id", "location_id"),
        Index("idx_media_attachments_created_at", "created_at"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(BigInteger)
    ticket_key: Mapped[str | None] = mapped_column(Text)
    hotel_id: Mapped[int | None] = mapped_column(BigInteger)
    location_id: Mapped[int | None] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(Text)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    max_file_id: Mapped[str | None] = mapped_column(Text)
    max_attachment_id: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    public_url: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class KnowledgeArticle(Base):
    """Статья базы знаний HelpDesk."""

    __tablename__ = "knowledge_articles"
    __table_args__ = (
        Index(
            "idx_knowledge_articles_scope_category_active",
            "scope_id",
            "category_id",
            "is_active",
            "sort_order",
            "created_at",
        ),
        Index("idx_helpdesk_knowledge_articles_source_ticket", "source_ticket_key"),
        Index("idx_helpdesk_knowledge_articles_source_location", "source_location_id"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("helpdesk.knowledge_scopes.id"),
        nullable=False,
    )
    hotel_id: Mapped[int | None] = mapped_column(BigInteger)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_ticket_key: Mapped[str | None] = mapped_column(Text)
    source_location_id: Mapped[int | None] = mapped_column(BigInteger)
    author_user_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
class KnowledgeScope(Base):
    """Раздел верхнего уровня для базы знаний."""

    __tablename__ = "knowledge_scopes"
    __table_args__ = (
        Index("idx_helpdesk_knowledge_scopes_active_sort", "is_active", "sort_order"),
        {"schema": "helpdesk"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    hotel_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = [
    "KnowledgeScope",
    "MediaAttachment",
    "Ticket",
    "TicketAttachment",
    "TicketComment",
    "TicketEvent",
    "KnowledgeArticle",
]
