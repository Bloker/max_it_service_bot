"""SQLAlchemy models существующих PostgreSQL таблиц."""

from app.db.base import Base
from app.db.models.helpdesk import (
    KnowledgeArticle,
    KnowledgeScope,
    MediaAttachment,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketEvent,
)
from app.db.models.network import NetworkToolRun
from app.db.models.ops import AuditLog

__all__ = [
    "AuditLog",
    "Base",
    "KnowledgeArticle",
    "KnowledgeScope",
    "MediaAttachment",
    "NetworkToolRun",
    "Ticket",
    "TicketAttachment",
    "TicketComment",
    "TicketEvent",
]
