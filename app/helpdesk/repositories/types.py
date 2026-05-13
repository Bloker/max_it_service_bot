"""Общие типы результатов репозиториев HelpDesk."""

from dataclasses import dataclass

from app.helpdesk.models.ticket import Ticket


@dataclass(slots=True)
class TicketActionResult:
    """Единый результат операций над заявкой."""

    ok: bool
    reason: str
    ticket: Ticket | None = None
