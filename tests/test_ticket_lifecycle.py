import asyncio
import unittest

from app.helpdesk.models.ticket import TicketStatus
from app.helpdesk.repositories.in_memory_ticket_repository import InMemoryTicketRepository
from app.helpdesk.services.ticket_lifecycle_service import TicketLifecycleService


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


if __name__ == '__main__':
    unittest.main()
