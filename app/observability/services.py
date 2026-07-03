"""Сервисный слой audit/events с graceful fallback."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.observability.models import AuditRecord, NetworkToolRunRecord, TicketEventRecord
from app.observability.repositories.observability_repository import ObservabilityRepository

logger = logging.getLogger(__name__)


class ObservabilityService:
    """Пишет события, не ломая основной бизнес-сценарий при ошибках БД."""

    def __init__(
        self,
        *,
        repository: ObservabilityRepository | None = None,
        audit_enabled: bool = True,
        ticket_events_enabled: bool = True,
        network_tool_runs_enabled: bool = True,
    ) -> None:
        self._repository = repository
        self._audit_enabled = audit_enabled
        self._ticket_events_enabled = ticket_events_enabled
        self._network_tool_runs_enabled = network_tool_runs_enabled

    async def ticket_event(
        self,
        *,
        ticket_id: str,
        event_type: str,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        source: str | None = None,
        related_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Пишет бизнес-событие заявки."""

        if not self._ticket_events_enabled or self._repository is None:
            return
        record = TicketEventRecord(
            ticket_id=ticket_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            actor_role=actor_role,
            old_status=old_status,
            new_status=new_status,
            source=source,
            related_message_id=related_message_id,
            metadata=metadata or {},
        )
        try:
            self._repository.record_ticket_event(record)
        except Exception:
            logger.warning(
                "Ticket event write failed: ticket_id=%s event_type=%s",
                ticket_id,
                event_type,
                exc_info=True,
            )

    async def audit(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        result: str,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Пишет audit record."""

        if not self._audit_enabled or self._repository is None:
            return
        record = AuditRecord(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
            metadata=metadata or {},
        )
        try:
            self._repository.record_audit(record)
        except Exception:
            logger.warning(
                "Audit write failed: action=%s resource_type=%s resource_id=%s",
                action,
                resource_type,
                resource_id,
                exc_info=True,
            )

    async def network_tool_run(
        self,
        *,
        tool: str,
        target: str,
        status: str,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
        normalized_target: str | None = None,
        policy_decision: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        duration_ms: int | None = None,
        output_excerpt: str | None = None,
        output_truncated: bool = False,
        error_text: str | None = None,
        feature_enabled: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Пишет результат запуска сетевого инструмента."""

        if not self._network_tool_runs_enabled or self._repository is None:
            return
        now = datetime.now(tz=timezone.utc)
        record = NetworkToolRunRecord(
            tool=tool,
            target=target,
            status=status,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            normalized_target=normalized_target,
            policy_decision=policy_decision,
            started_at=started_at or now,
            finished_at=finished_at or now,
            duration_ms=duration_ms,
            output_excerpt=output_excerpt,
            output_truncated=output_truncated,
            error_text=error_text,
            feature_enabled=feature_enabled,
            metadata=metadata or {},
        )
        try:
            self._repository.record_network_tool_run(record)
        except Exception:
            logger.warning(
                "Network tool run write failed: tool=%s status=%s",
                tool,
                status,
                exc_info=True,
            )


def truncate_for_observability(value: str, limit: int = 500) -> tuple[str, bool]:
    """Ограничивает текст для audit/tool_runs без сохранения длинного output."""

    text = value or ""
    if len(text) <= limit:
        return text, False
    return f"{text[:limit].rstrip()}...", True
