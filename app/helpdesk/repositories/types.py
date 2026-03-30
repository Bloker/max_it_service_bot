from dataclasses import dataclass

from app.helpdesk.models.ticket import Ticket


@dataclass(slots=True)
class TicketActionResult:
    ok: bool
    reason: str
    ticket: Ticket | None = None

