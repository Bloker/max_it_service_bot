from collections.abc import Iterable
from typing import Protocol

from app.helpdesk.models.ticket import Ticket
from app.helpdesk.repositories.types import TicketActionResult


class TicketRepository(Protocol):
    async def create_ticket(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None = None,
        requester_department: str | None = None,
    ) -> Ticket: ...

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None: ...

    async def list_by_user(self, user_id: int, limit: int = 10) -> list[Ticket]: ...
    async def list_open(self, limit: int = 50) -> list[Ticket]: ...
    async def update_status(self, ticket_id: str, status: str) -> TicketActionResult: ...

    async def assign(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult: ...

    async def release(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult: ...

    async def close(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult: ...

    async def request_clarification(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult: ...
