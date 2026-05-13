"""Сервис жизненного цикла заявок HelpDesk."""

import logging
from collections.abc import Iterable

from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.repositories.contracts import TicketRepository
from app.helpdesk.repositories.types import TicketActionResult


logger = logging.getLogger(__name__)


class TicketLifecycleService:
    """Оркестрирует жизненный цикл заявок поверх репозитория."""

    def __init__(self, repository: TicketRepository) -> None:
        self.repository = repository

    async def create_ticket(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None,
        requester_department: str | None,
    ) -> Ticket:
        """Создает заявку и пишет событие в лог."""

        ticket = await self.repository.create_ticket(
            requester_user_id=requester_user_id,
            requester_name=requester_name,
            category=category,
            text=text,
            requester_phone=requester_phone,
            requester_department=requester_department,
        )
        logger.info(
            "Ticket created: ticket_id=%s user_id=%s category=%s",
            ticket.ticket_id,
            requester_user_id,
            category,
        )
        return ticket

    async def get_ticket(self, ticket_id: str) -> Ticket | None:
        return await self.repository.get_by_ticket_id(ticket_id)

    async def list_user_tickets(
        self,
        user_id: int,
        limit: int = 10,
        include_closed: bool = False,
    ) -> list[Ticket]:
        """Возвращает заявки пользователя с опциональным показом закрытых."""

        tickets = await self.repository.list_by_user(user_id=user_id, limit=limit)
        if include_closed:
            return tickets
        return [ticket for ticket in tickets if ticket.status != TicketStatus.CLOSED]

    async def list_open_tickets(self, limit: int = 50) -> list[Ticket]:
        return await self.repository.list_open(limit=limit)

    async def set_ticket_status(self, ticket_id: str, status: str) -> TicketActionResult:
        """Меняет статус заявки через репозиторий."""

        result = await self.repository.update_status(ticket_id=ticket_id, status=status)
        if result.ok:
            logger.info("Ticket status changed: ticket_id=%s status=%s", ticket_id, status)
        else:
            logger.warning(
                "Ticket status change failed: ticket_id=%s status=%s reason=%s",
                ticket_id,
                status,
                result.reason,
            )
        return result

    async def take_ticket(
        self,
        ticket_id: str,
        specialist_user_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        """Назначает заявку на специалиста."""

        result = await self.repository.assign(
            ticket_id=ticket_id,
            specialist_id=specialist_user_id,
            specialist_name=specialist_name,
        )
        if result.ok:
            logger.info("Ticket assigned: ticket_id=%s specialist_id=%s", ticket_id, specialist_user_id)
        else:
            logger.warning(
                "Ticket assign failed: ticket_id=%s specialist_id=%s reason=%s",
                ticket_id,
                specialist_user_id,
                result.reason,
            )
        return result

    async def release_ticket(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        """Освобождает заявку от исполнителя."""

        result = await self.repository.release(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            admin_ids=admin_ids,
        )
        if result.ok:
            logger.info("Ticket released: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
        else:
            logger.warning(
                "Ticket release failed: ticket_id=%s actor_id=%s reason=%s",
                ticket_id,
                actor_user_id,
                result.reason,
            )
        return result

    async def close_ticket(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        """Закрывает заявку от имени администратора или исполнителя."""

        result = await self.repository.close(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        if result.ok:
            logger.info("Ticket closed: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
        else:
            logger.warning(
                "Ticket close failed: ticket_id=%s actor_id=%s reason=%s",
                ticket_id,
                actor_user_id,
                result.reason,
            )
        return result

    async def request_clarification(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        """Переводит заявку в ожидание уточнения от пользователя."""

        result = await self.repository.request_clarification(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        if result.ok:
            logger.info("Ticket moved to waiting_user: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
        else:
            logger.warning(
                "Ticket clarify failed: ticket_id=%s actor_id=%s reason=%s",
                ticket_id,
                actor_user_id,
                result.reason,
            )
        return result
