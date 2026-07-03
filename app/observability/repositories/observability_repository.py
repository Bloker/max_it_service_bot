"""Контракт постоянного хранения audit/events."""

from typing import Protocol

from app.observability.models import AuditRecord, NetworkToolRunRecord, TicketEventRecord


class ObservabilityRepository(Protocol):
    """Единый контракт записи бизнес-событий и audit."""

    def record_ticket_event(self, record: TicketEventRecord) -> None: ...

    def record_audit(self, record: AuditRecord) -> None: ...

    def record_network_tool_run(self, record: NetworkToolRunRecord) -> None: ...
