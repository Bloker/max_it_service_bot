import unittest
from datetime import datetime, timezone

from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.texts.specialist_texts import render_open_tickets_list
from app.helpdesk.texts.user_texts import render_ticket_closed_notification


class SpecialistTextsTests(unittest.TestCase):
    def test_render_open_tickets_list_formats_tickets_as_html_blocks(self) -> None:
        tickets = [
            Ticket(
                id="T-00001",
                user_id=101,
                category="Доступы и учетные записи",
                text="Test",
                status=TicketStatus.IN_PROGRESS,
                assignee_name="Дмитрий",
            ),
            Ticket(
                id="T-00002",
                user_id=102,
                category="ПК <ПО>",
                text="Test",
                status=TicketStatus.NEW,
            ),
        ]

        text = render_open_tickets_list(tickets)

        self.assertIn("<b>Не закрытые заявки</b>", text)
        self.assertIn("Всего: <b>2</b>", text)
        self.assertIn("<b>1. <code>T-00001</code></b>", text)
        self.assertIn("Статус: <b>в работе</b>", text)
        self.assertIn("Исполнитель: Дмитрий", text)
        self.assertIn("Категория: ПК &lt;ПО&gt;", text)

    def test_render_open_tickets_list_handles_empty_list(self) -> None:
        self.assertEqual(render_open_tickets_list([]), "Открытых заявок нет.")

    def test_render_ticket_closed_notification_formats_created_date(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="Доступы",
            text="Test",
            created_at=datetime(2026, 5, 13, 7, 30, tzinfo=timezone.utc),
        )

        text = render_ticket_closed_notification(ticket)

        self.assertEqual(text, "Заявка №T-00001 от 13.05.2026 10:30 выполнена.")


if __name__ == "__main__":
    unittest.main()
