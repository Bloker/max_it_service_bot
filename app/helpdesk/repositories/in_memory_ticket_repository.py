"""In-memory реализация репозитория заявок."""

import asyncio
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone

from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.repositories.types import TicketActionResult


class InMemoryTicketRepository:
    """In-memory репозиторий заявок для тестов и локального режима."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counter = 0
        self._tickets_by_id: dict[str, Ticket] = {}
        self._tickets_by_user: dict[int, list[str]] = defaultdict(list)

    async def create_ticket(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None = None,
        requester_department: str | None = None,
    ) -> Ticket:
        """Создает заявку с последовательным человекочитаемым ID."""

        async with self._lock:
            self._counter += 1
            ticket_id = f"T-{self._counter:05d}"
            now = datetime.now(tz=timezone.utc)
            ticket = Ticket(
                id=ticket_id,
                user_id=requester_user_id,
                requester_name=requester_name,
                category=category,
                text=text,
                created_at=now,
                updated_at=now,
                requester_phone=requester_phone,
                requester_department=requester_department,
            )
            self._tickets_by_id[ticket_id] = ticket
            self._tickets_by_user[requester_user_id].append(ticket_id)
            return ticket

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        async with self._lock:
            return self._tickets_by_id.get(ticket_id)

    async def list_by_user(self, user_id: int, limit: int = 10) -> list[Ticket]:
        async with self._lock:
            ids = self._tickets_by_user.get(user_id, [])
            latest_ids = ids[-limit:]
            return [self._tickets_by_id[ticket_id] for ticket_id in reversed(latest_ids)]

    async def list_open(self, limit: int = 50) -> list[Ticket]:
        async with self._lock:
            tickets = [
                ticket
                for ticket in self._tickets_by_id.values()
                if ticket.status != TicketStatus.CLOSED
            ]
            tickets.sort(key=lambda t: t.updated_at, reverse=True)
            return tickets[:limit]

    async def update_status(self, ticket_id: str, status: str) -> TicketActionResult:
        async with self._lock:
            ticket = self._tickets_by_id.get(ticket_id)
            if ticket is None:
                return TicketActionResult(ok=False, reason="not_found")
            try:
                ticket.status = TicketStatus(status)
            except ValueError:
                return TicketActionResult(ok=False, reason="invalid_status", ticket=ticket)
            ticket.updated_at = datetime.now(tz=timezone.utc)
            return TicketActionResult(ok=True, reason="status_updated", ticket=ticket)

    async def reopen(self, ticket_id: str) -> TicketActionResult:
        """Повторно открывает закрытую заявку, сохраняя исполнителя."""

        async with self._lock:
            ticket = self._tickets_by_id.get(ticket_id)
            if ticket is None:
                return TicketActionResult(ok=False, reason="not_found")
            if ticket.status != TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_open", ticket=ticket)
            ticket.status = (
                TicketStatus.IN_PROGRESS if ticket.assigned_to else TicketStatus.NEW
            )
            ticket.updated_at = datetime.now(tz=timezone.utc)
            return TicketActionResult(ok=True, reason="reopened", ticket=ticket)

    async def assign(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        async with self._lock:
            ticket = self._tickets_by_id.get(ticket_id)
            if ticket is None:
                return TicketActionResult(ok=False, reason="not_found")

            if ticket.status == TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)

            if ticket.assigned_to and ticket.assigned_to != specialist_id:
                return TicketActionResult(ok=False, reason="already_assigned", ticket=ticket)

            ticket.assigned_to = specialist_id
            ticket.assignee_name = specialist_name
            ticket.status = TicketStatus.IN_PROGRESS
            ticket.updated_at = datetime.now(tz=timezone.utc)
            return TicketActionResult(ok=True, reason="assigned", ticket=ticket)

    async def release(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        async with self._lock:
            ticket = self._tickets_by_id.get(ticket_id)
            if ticket is None:
                return TicketActionResult(ok=False, reason="not_found")

            if ticket.assigned_to is None:
                return TicketActionResult(ok=False, reason="not_assigned", ticket=ticket)

            is_admin = actor_user_id in set(admin_ids)
            if ticket.assigned_to != actor_user_id and not is_admin:
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)

            ticket.assigned_to = None
            ticket.assignee_name = None
            if ticket.status != TicketStatus.CLOSED:
                ticket.status = TicketStatus.NEW
            ticket.updated_at = datetime.now(tz=timezone.utc)
            return TicketActionResult(ok=True, reason="released", ticket=ticket)

    async def close(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        async with self._lock:
            ticket = self._tickets_by_id.get(ticket_id)
            if ticket is None:
                return TicketActionResult(ok=False, reason="not_found")

            if ticket.status == TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)

            is_admin = actor_user_id in set(admin_ids)
            if ticket.assigned_to and ticket.assigned_to != actor_user_id and not is_admin:
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)

            if ticket.assigned_to is None:
                ticket.assigned_to = actor_user_id
                ticket.assignee_name = actor_name

            ticket.status = TicketStatus.CLOSED
            ticket.updated_at = datetime.now(tz=timezone.utc)
            return TicketActionResult(ok=True, reason="closed", ticket=ticket)

    async def request_clarification(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        async with self._lock:
            ticket = self._tickets_by_id.get(ticket_id)
            if ticket is None:
                return TicketActionResult(ok=False, reason="not_found")

            if ticket.status == TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)

            is_admin = actor_user_id in set(admin_ids)
            if ticket.assigned_to and ticket.assigned_to != actor_user_id and not is_admin:
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)

            if ticket.assigned_to is None:
                ticket.assigned_to = actor_user_id
                ticket.assignee_name = actor_name

            ticket.status = TicketStatus.WAITING_USER
            ticket.updated_at = datetime.now(tz=timezone.utc)
            return TicketActionResult(ok=True, reason="waiting_user", ticket=ticket)
