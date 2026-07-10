"""Доменные модели базы знаний HelpDesk."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class KnowledgeScopeType(StrEnum):
    """Тип раздела базы знаний."""

    HOTEL = "hotel"
    GLOBAL = "global"
    INFRASTRUCTURE = "infrastructure"
    SYSTEM = "system"


@dataclass(slots=True, frozen=True)
class KnowledgeScope:
    """Раздел базы знаний верхнего уровня."""

    id: int
    code: str
    title: str
    scope_type: KnowledgeScopeType
    hotel_id: int | None = None
    is_active: bool = True
    sort_order: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass(slots=True, frozen=True)
class KnowledgeArticle:
    """Статья базы знаний."""

    id: int
    scope_id: int
    hotel_id: int | None
    category_id: int
    title: str
    body: str
    source_ticket_key: str | None = None
    source_location_id: int | None = None
    author_user_id: int | None = None
    is_active: bool = True
    sort_order: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
