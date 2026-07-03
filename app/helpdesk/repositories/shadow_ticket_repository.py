"""Shadow-read wrapper для безопасной сверки legacy и normalized tickets."""

import logging
from collections.abc import Iterable

from app.helpdesk.models.ticket import Ticket
from app.helpdesk.repositories.contracts import TicketRepository
from app.helpdesk.repositories.types import TicketActionResult


logger = logging.getLogger(__name__)


class ShadowReadTicketRepository:
    """Пишет в legacy, а normalized использует только для контрольного чтения."""

    def __init__(
        self,
        *,
        primary: TicketRepository,
        shadow: TicketRepository,
    ) -> None:
        self._primary = primary
        self._shadow = shadow

    async def create_ticket(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None = None,
        requester_department: str | None = None,
    ) -> Ticket:
        ticket = await self._primary.create_ticket(
            requester_user_id=requester_user_id,
            requester_name=requester_name,
            category=category,
            text=text,
            requester_phone=requester_phone,
            requester_department=requester_department,
        )
        await self._compare_ticket(ticket.ticket_id, primary_ticket=ticket)
        return ticket

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        ticket = await self._primary.get_by_ticket_id(ticket_id)
        await self._compare_ticket(ticket_id, primary_ticket=ticket)
        return ticket

    async def list_by_user(self, user_id: int, limit: int = 10) -> list[Ticket]:
        tickets = await self._primary.list_by_user(user_id=user_id, limit=limit)
        await self._compare_ticket_lists("list_by_user", tickets, self._shadow.list_by_user, user_id, limit)
        return tickets

    async def list_open(self, limit: int = 50) -> list[Ticket]:
        tickets = await self._primary.list_open(limit=limit)
        await self._compare_ticket_lists("list_open", tickets, self._shadow.list_open, limit)
        return tickets

    async def update_status(self, ticket_id: str, status: str) -> TicketActionResult:
        result = await self._primary.update_status(ticket_id=ticket_id, status=status)
        await self._compare_ticket(ticket_id, primary_ticket=result.ticket)
        return result

    async def assign(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        result = await self._primary.assign(
            ticket_id=ticket_id,
            specialist_id=specialist_id,
            specialist_name=specialist_name,
        )
        await self._compare_ticket(ticket_id, primary_ticket=result.ticket)
        return result

    async def release(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        result = await self._primary.release(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            admin_ids=admin_ids,
        )
        await self._compare_ticket(ticket_id, primary_ticket=result.ticket)
        return result

    async def close(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        result = await self._primary.close(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        await self._compare_ticket(ticket_id, primary_ticket=result.ticket)
        return result

    async def request_clarification(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        result = await self._primary.request_clarification(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        await self._compare_ticket(ticket_id, primary_ticket=result.ticket)
        return result

    async def _compare_ticket(
        self,
        ticket_id: str,
        *,
        primary_ticket: Ticket | None,
    ) -> None:
        try:
            shadow_ticket = await self._shadow.get_by_ticket_id(ticket_id)
        except Exception:
            logger.warning("Ticket shadow read failed: ticket_id=%s", ticket_id, exc_info=True)
            return

        mismatch = _ticket_mismatch(primary_ticket, shadow_ticket)
        if mismatch:
            logger.warning(
                "Ticket shadow mismatch: ticket_id=%s fields=%s",
                ticket_id,
                ",".join(mismatch),
            )

    async def _compare_ticket_lists(self, label: str, primary_tickets: list[Ticket], method, *args) -> None:
        try:
            shadow_tickets = await method(*args)
        except Exception:
            logger.warning("Ticket shadow list read failed: operation=%s", label, exc_info=True)
            return
        primary_ids = [ticket.ticket_id for ticket in primary_tickets]
        shadow_ids = [ticket.ticket_id for ticket in shadow_tickets]
        if primary_ids != shadow_ids:
            logger.warning(
                "Ticket shadow list mismatch: operation=%s primary_count=%s shadow_count=%s",
                label,
                len(primary_ids),
                len(shadow_ids),
            )


def _ticket_mismatch(primary: Ticket | None, shadow: Ticket | None) -> list[str]:
    if primary is None and shadow is None:
        return []
    if primary is None or shadow is None:
        return ["presence"]
    fields: list[str] = []
    if primary.ticket_id != shadow.ticket_id:
        fields.append("ticket_key")
    if primary.status != shadow.status:
        fields.append("status")
    if primary.category != shadow.category:
        fields.append("category")
    if primary.user_id != shadow.user_id:
        fields.append("requester_user_id")
    if primary.assigned_to != shadow.assigned_to:
        fields.append("assignee_user_id")
    if primary.created_at != shadow.created_at:
        fields.append("created_at")
    return fields


__all__ = ["ShadowReadTicketRepository"]
