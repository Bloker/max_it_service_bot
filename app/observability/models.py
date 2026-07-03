"""Модели записей audit/events без привязки к конкретной БД."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TicketEventRecord:
    """Бизнес-событие заявки HelpDesk."""

    ticket_id: str
    event_type: str
    actor_user_id: int | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    old_status: str | None = None
    new_status: str | None = None
    source: str | None = None
    related_message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuditRecord:
    """Операционный audit record."""

    action: str
    resource_type: str
    resource_id: str
    result: str
    actor_user_id: int | None = None
    actor_role: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NetworkToolRunRecord:
    """Результат запуска сетевого инструмента."""

    tool: str
    target: str
    status: str
    actor_user_id: int | None = None
    actor_name: str | None = None
    normalized_target: str | None = None
    policy_decision: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    output_excerpt: str | None = None
    output_truncated: bool = False
    error_text: str | None = None
    feature_enabled: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
