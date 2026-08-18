"""Сервис жизненного цикла заявок HelpDesk."""

import logging
from collections.abc import Iterable

from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.repositories.contracts import TicketRepository
from app.helpdesk.repositories.types import TicketActionResult
from app.observability.services import ObservabilityService


logger = logging.getLogger(__name__)

_STATUS_CODES = {
    TicketStatus.NEW: "new",
    TicketStatus.IN_PROGRESS: "in_progress",
    TicketStatus.WAITING_USER: "waiting_user",
    TicketStatus.CLOSED: "closed",
}


class TicketLifecycleService:
    """Оркестрирует жизненный цикл заявок поверх репозитория."""

    def __init__(
        self,
        repository: TicketRepository,
        observability: ObservabilityService | None = None,
    ) -> None:
        self.repository = repository
        self.observability = observability

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
        await self._ticket_event(
            ticket_id=ticket.ticket_id,
            event_type="ticket_created",
            actor_user_id=requester_user_id,
            actor_name=requester_name,
            actor_role="user",
            new_status=_status_code(ticket.status),
            source="user_message",
            metadata={"category": category, "has_phone": bool(requester_phone)},
        )
        await self._audit(
            action="ticket_created",
            resource_id=ticket.ticket_id,
            result="success",
            actor_user_id=requester_user_id,
            actor_role="user",
            metadata={"category": category},
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

    async def reopen_ticket(
        self,
        ticket_id: str,
        *,
        actor_user_id: int,
        actor_name: str,
    ) -> TicketActionResult:
        """Повторно открывает заявку и пишет одно доменное событие."""

        result = await self.repository.reopen(ticket_id=ticket_id)
        if not result.ok:
            await self._audit(
                action="ticket_reopened",
                resource_id=ticket_id,
                result="failed",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                reason=result.reason,
            )
            return result
        ticket = result.ticket
        logger.info("Ticket reopened: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
        await self._ticket_event(
            ticket_id=ticket_id,
            event_type="ticket_reopened",
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            actor_role="IT specialist",
            old_status="closed",
            new_status=_status_code(ticket.status) if ticket else None,
            source="callback",
            metadata={"assignee_preserved": bool(ticket and ticket.assigned_to)},
        )
        await self._audit(
            action="ticket_reopened",
            resource_id=ticket_id,
            result="success",
            actor_user_id=actor_user_id,
            actor_role="IT specialist",
        )
        return result

    async def set_ticket_status(self, ticket_id: str, status: str) -> TicketActionResult:
        """Меняет статус заявки через репозиторий."""

        before = await self.repository.get_by_ticket_id(ticket_id)
        before_status = _status_code(before.status) if before else None
        result = await self.repository.update_status(ticket_id=ticket_id, status=status)
        if result.ok:
            logger.info("Ticket status changed: ticket_id=%s status=%s", ticket_id, status)
            await self._ticket_event(
                ticket_id=ticket_id,
                event_type="ticket_status_changed",
                old_status=before_status,
                new_status=_status_code(result.ticket.status) if result.ticket else _status_code(status),
                source="system",
                metadata={"reason": result.reason},
            )
        else:
            logger.warning(
                "Ticket status change failed: ticket_id=%s status=%s reason=%s",
                ticket_id,
                status,
                result.reason,
            )
            await self._audit(
                action="ticket_status_changed",
                resource_id=ticket_id,
                result="failed",
                reason=result.reason,
                metadata={"requested_status": status},
            )
        return result

    async def take_ticket(
        self,
        ticket_id: str,
        specialist_user_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        """Назначает заявку на специалиста."""

        before = await self.repository.get_by_ticket_id(ticket_id)
        before_status = _status_code(before.status) if before else None
        result = await self.repository.assign(
            ticket_id=ticket_id,
            specialist_id=specialist_user_id,
            specialist_name=specialist_name,
        )
        if result.ok:
            logger.info("Ticket assigned: ticket_id=%s specialist_id=%s", ticket_id, specialist_user_id)
            await self._ticket_event(
                ticket_id=ticket_id,
                event_type="ticket_assigned",
                actor_user_id=specialist_user_id,
                actor_name=specialist_name,
                actor_role="IT specialist",
                old_status=before_status,
                new_status=_status_code(result.ticket.status) if result.ticket else "in_progress",
                source="callback",
                metadata={"assigned_to": specialist_user_id},
            )
            await self._status_changed_if_needed(
                ticket_id=ticket_id,
                actor_user_id=specialist_user_id,
                actor_name=specialist_name,
                actor_role="IT specialist",
                before=before,
                before_status=before_status,
                after=result.ticket,
                source="callback",
            )
            await self._audit(
                action="ticket_assigned",
                resource_id=ticket_id,
                result="success",
                actor_user_id=specialist_user_id,
                actor_role="IT specialist",
            )
        else:
            logger.warning(
                "Ticket assign failed: ticket_id=%s specialist_id=%s reason=%s",
                ticket_id,
                specialist_user_id,
                result.reason,
            )
            await self._audit(
                action="ticket_assigned",
                resource_id=ticket_id,
                result="failed",
                actor_user_id=specialist_user_id,
                actor_role="IT specialist",
                reason=result.reason,
            )
        return result

    async def release_ticket(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        """Освобождает заявку от исполнителя."""

        before = await self.repository.get_by_ticket_id(ticket_id)
        before_status = _status_code(before.status) if before else None
        result = await self.repository.release(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            admin_ids=admin_ids,
        )
        if result.ok:
            logger.info("Ticket released: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
            await self._ticket_event(
                ticket_id=ticket_id,
                event_type="ticket_released",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                old_status=before_status,
                new_status=_status_code(result.ticket.status) if result.ticket else "new",
                source="callback",
            )
            await self._status_changed_if_needed(
                ticket_id=ticket_id,
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                before=before,
                before_status=before_status,
                after=result.ticket,
                source="callback",
            )
            await self._audit(
                action="ticket_released",
                resource_id=ticket_id,
                result="success",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
            )
        else:
            logger.warning(
                "Ticket release failed: ticket_id=%s actor_id=%s reason=%s",
                ticket_id,
                actor_user_id,
                result.reason,
            )
            await self._audit(
                action="ticket_released",
                resource_id=ticket_id,
                result="failed",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                reason=result.reason,
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

        before = await self.repository.get_by_ticket_id(ticket_id)
        before_status = _status_code(before.status) if before else None
        result = await self.repository.close(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        if result.ok:
            logger.info("Ticket closed: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
            await self._ticket_event(
                ticket_id=ticket_id,
                event_type="ticket_closed",
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_role="IT specialist",
                old_status=before_status,
                new_status=_status_code(result.ticket.status) if result.ticket else "closed",
                source="callback",
            )
            await self._status_changed_if_needed(
                ticket_id=ticket_id,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_role="IT specialist",
                before=before,
                before_status=before_status,
                after=result.ticket,
                source="callback",
            )
            await self._audit(
                action="ticket_closed",
                resource_id=ticket_id,
                result="success",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
            )
        else:
            logger.warning(
                "Ticket close failed: ticket_id=%s actor_id=%s reason=%s",
                ticket_id,
                actor_user_id,
                result.reason,
            )
            await self._audit(
                action="ticket_closed",
                resource_id=ticket_id,
                result="failed",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                reason=result.reason,
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

        before = await self.repository.get_by_ticket_id(ticket_id)
        before_status = _status_code(before.status) if before else None
        result = await self.repository.request_clarification(
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        if result.ok:
            logger.info("Ticket moved to waiting_user: ticket_id=%s actor_id=%s", ticket_id, actor_user_id)
            await self._ticket_event(
                ticket_id=ticket_id,
                event_type="ticket_waiting_user",
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_role="IT specialist",
                old_status=before_status,
                new_status=_status_code(result.ticket.status) if result.ticket else "waiting_user",
                source="callback",
            )
            await self._status_changed_if_needed(
                ticket_id=ticket_id,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                actor_role="IT specialist",
                before=before,
                before_status=before_status,
                after=result.ticket,
                source="callback",
            )
            await self._audit(
                action="clarification_requested",
                resource_id=ticket_id,
                result="success",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
            )
        else:
            logger.warning(
                "Ticket clarify failed: ticket_id=%s actor_id=%s reason=%s",
                ticket_id,
                actor_user_id,
                result.reason,
            )
            await self._audit(
                action="clarification_requested",
                resource_id=ticket_id,
                result="failed",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                reason=result.reason,
            )
        return result

    async def _status_changed_if_needed(
        self,
        *,
        ticket_id: str,
        before: Ticket | None,
        before_status: str | None,
        after: Ticket | None,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        source: str | None = None,
    ) -> None:
        """Пишет ticket_status_changed, если статус реально изменился."""

        after_status = _status_code(after.status) if after else None
        if before_status is None or after_status is None or before_status == after_status:
            return
        await self._ticket_event(
            ticket_id=ticket_id,
            event_type="ticket_status_changed",
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            actor_role=actor_role,
            old_status=before_status,
            new_status=after_status,
            source=source,
        )

    async def _ticket_event(self, **kwargs) -> None:
        """Прокидывает событие в observability, если сервис подключен."""

        if self.observability is None:
            return
        await self.observability.ticket_event(**kwargs)

    async def _audit(self, **kwargs) -> None:
        """Прокидывает audit record в observability, если сервис подключен."""

        if self.observability is None:
            return
        kwargs.setdefault("resource_type", "ticket")
        await self.observability.audit(**kwargs)


def _status_code(status: TicketStatus | str) -> str:
    """Преобразует display-статус legacy в нормализованный status_code."""

    try:
        normalized = status if isinstance(status, TicketStatus) else TicketStatus(str(status))
    except ValueError:
        return str(status)
    return _STATUS_CODES[normalized]
