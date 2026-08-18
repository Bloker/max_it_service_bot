import asyncio
import unittest

from app.helpdesk.models.ticket import TicketStatus
from app.helpdesk.repositories.in_memory_ticket_repository import InMemoryTicketRepository
from app.helpdesk.services.ticket_lifecycle_service import TicketLifecycleService
from app.observability.services import ObservabilityService
from tests.test_observability_service import FakeObservabilityRepository


class TicketLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = InMemoryTicketRepository()
        self.service = TicketLifecycleService(self.repository)

    async def test_create_take_clarify_close_flow(self) -> None:
        ticket = await self.service.create_ticket(
            requester_user_id=101,
            requester_name='User',
            category='Сеть / Wi-Fi',
            text='Нет доступа',
            requester_phone=None,
            requester_department=None,
        )
        self.assertEqual(ticket.status, TicketStatus.NEW)

        take = await self.service.take_ticket(ticket.ticket_id, 501, 'Spec')
        self.assertTrue(take.ok)
        self.assertEqual(take.ticket.status, TicketStatus.IN_PROGRESS)

        clarify = await self.service.request_clarification(
            ticket.ticket_id,
            actor_user_id=501,
            actor_name='Spec',
            admin_ids=(),
        )
        self.assertTrue(clarify.ok)
        self.assertEqual(clarify.ticket.status, TicketStatus.WAITING_USER)

        close = await self.service.close_ticket(
            ticket.ticket_id,
            actor_user_id=501,
            actor_name='Spec',
            admin_ids=(),
        )
        self.assertTrue(close.ok)
        self.assertEqual(close.ticket.status, TicketStatus.CLOSED)

    async def test_open_tickets_excludes_closed(self) -> None:
        t1 = await self.service.create_ticket(1, 'A', 'cat', 'text', None, None)
        t2 = await self.service.create_ticket(2, 'B', 'cat', 'text', None, None)

        await self.service.close_ticket(t1.ticket_id, actor_user_id=777, actor_name='Admin', admin_ids=(777,))
        open_tickets = await self.service.list_open_tickets(limit=10)
        ids = {t.ticket_id for t in open_tickets}

        self.assertIn(t2.ticket_id, ids)
        self.assertNotIn(t1.ticket_id, ids)

    async def test_list_user_tickets_excludes_closed_by_default(self) -> None:
        t1 = await self.service.create_ticket(101, 'User', 'cat', 'open ticket', None, None)
        t2 = await self.service.create_ticket(101, 'User', 'cat', 'closed ticket', None, None)
        await self.service.close_ticket(
            t2.ticket_id,
            actor_user_id=777,
            actor_name='Admin',
            admin_ids=(777,),
        )

        tickets = await self.service.list_user_tickets(user_id=101, limit=20)
        ids = {ticket.ticket_id for ticket in tickets}
        self.assertIn(t1.ticket_id, ids)
        self.assertNotIn(t2.ticket_id, ids)

        all_tickets = await self.service.list_user_tickets(
            user_id=101,
            limit=20,
            include_closed=True,
        )
        all_ids = {ticket.ticket_id for ticket in all_tickets}
        self.assertIn(t1.ticket_id, all_ids)
        self.assertIn(t2.ticket_id, all_ids)

    async def test_lifecycle_writes_business_events(self) -> None:
        repository = FakeObservabilityRepository()
        service = TicketLifecycleService(
            InMemoryTicketRepository(),
            observability=ObservabilityService(repository=repository),
        )

        ticket = await service.create_ticket(101, "User", "cat", "text", None, None)
        await service.take_ticket(ticket.ticket_id, 501, "Spec")

        event_types = [item.event_type for item in repository.ticket_events]
        audit_actions = [item.action for item in repository.audit_records]
        self.assertIn("ticket_created", event_types)
        self.assertIn("ticket_assigned", event_types)
        self.assertIn("ticket_status_changed", event_types)
        status_event = next(
            item
            for item in repository.ticket_events
            if item.event_type == "ticket_status_changed"
        )
        self.assertEqual(status_event.old_status, "new")
        self.assertEqual(status_event.new_status, "in_progress")
        self.assertIn("ticket_created", audit_actions)
        self.assertIn("ticket_assigned", audit_actions)

    async def test_reopen_preserves_assignee_and_is_idempotent(self) -> None:
        repository = FakeObservabilityRepository()
        service = TicketLifecycleService(
            InMemoryTicketRepository(),
            observability=ObservabilityService(repository=repository),
        )
        ticket = await service.create_ticket(101, "User", "cat", "text", None, None)
        await service.take_ticket(ticket.ticket_id, 501, "Spec")
        await service.close_ticket(ticket.ticket_id, 501, "Spec", ())

        reopened = await service.reopen_ticket(
            ticket.ticket_id,
            actor_user_id=777,
            actor_name="Admin",
        )
        duplicate = await service.reopen_ticket(
            ticket.ticket_id,
            actor_user_id=777,
            actor_name="Admin",
        )

        self.assertTrue(reopened.ok)
        self.assertEqual(reopened.ticket.status, TicketStatus.IN_PROGRESS)
        self.assertEqual(reopened.ticket.assigned_to, 501)
        self.assertFalse(duplicate.ok)
        self.assertEqual(duplicate.reason, "already_open")
        events = [item for item in repository.ticket_events if item.event_type == "ticket_reopened"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].old_status, "closed")
        self.assertEqual(events[0].new_status, "in_progress")
        self.assertTrue(events[0].metadata["assignee_preserved"])

    async def test_reopen_without_assignee_returns_to_new(self) -> None:
        ticket = await self.service.create_ticket(101, "User", "cat", "text", None, None)
        await self.service.close_ticket(ticket.ticket_id, 777, "Admin", (777,))
        await self.service.release_ticket(ticket.ticket_id, 777, (777,))
        # Закрытая заявка обычно сохраняет назначившегося при закрытии. Для
        # проверки ветки без исполнителя воспроизводим legacy-запись напрямую.
        ticket.assigned_to = None
        ticket.assignee_name = None
        result = await self.service.reopen_ticket(
            ticket.ticket_id,
            actor_user_id=777,
            actor_name="Admin",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.ticket.status, TicketStatus.NEW)


if __name__ == '__main__':
    unittest.main()
