import unittest
from datetime import datetime, timezone

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.services.ticket_clarification_service import TicketClarificationService
from app.helpdesk.texts.specialist_texts import render_group_ticket, render_open_tickets_list
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

    def test_render_group_ticket_includes_last_clarification(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="VPN",
            text="Не работает & VPN",
            status=TicketStatus.WAITING_USER,
            assignee_name="Дмитрий",
        )
        clarification = TicketClarificationService().save_last(
            ticket_id="T-00001",
            actor_user_id=501,
            actor_name="Дмитрий",
            text="Что именно не работает <сейчас>?",
        )

        text = render_group_ticket(ticket, last_clarification=clarification)

        self.assertIn("Последнее уточнение:", text)
        self.assertIn("Дмитрий: Что именно не работает &lt;сейчас&gt;?", text)
        self.assertIn("Не работает &amp; VPN", text)

    def test_render_group_ticket_includes_attached_user_reply(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="VPN",
            text="Не работает",
            status=TicketStatus.WAITING_USER,
        )
        service = TicketClarificationService()
        service.save_user_reply_candidate(
            ticket_id="T-00001",
            user_id=101,
            user_name="Иван <И>",
            text="Теперь показывает ошибку & код",
            group_message_id="group-mid-1",
        )
        attached_reply = service.attach_user_reply("group-mid-1")

        text = render_group_ticket(ticket, attached_user_reply=attached_reply)

        self.assertIn("Ответ пользователя:", text)
        self.assertIn("Иван &lt;И&gt;: Теперь показывает ошибку &amp; код", text)

    def test_render_group_ticket_formats_ru_phone(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="VPN",
            text="Не работает",
            requester_name="ID 101",
            requester_phone="79530853578",
        )

        text = render_group_ticket(ticket)

        self.assertIn(
            'Пользователь: ID 101 (тел.: <a href="tel:+79530853578">'
            "+79530853578</a>)",
            text,
        )

    def test_render_group_ticket_formats_ru_phone_link_variants(self) -> None:
        cases = [
            "79649063437",
            "89649063437",
            "9649063437",
        ]

        for phone in cases:
            with self.subTest(phone=phone):
                ticket = Ticket(
                    id="T-00001",
                    user_id=101,
                    category="VPN",
                    text="Не работает",
                    requester_name="ID 101",
                    requester_phone=phone,
                )

                text = render_group_ticket(ticket)

                self.assertIn(
                    '<a href="tel:+79649063437">+79649063437</a>',
                    text,
                )

    def test_render_group_ticket_uses_missing_phone_text(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="VPN",
            text="Не работает",
            requester_name="ID 101",
        )

        text = render_group_ticket(ticket)

        self.assertIn("Пользователь: ID 101 (тел.: не указан)", text)
        self.assertNotIn('href="tel:', text)

    def test_render_group_ticket_escapes_text_with_phone_link(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="VPN <Corp>",
            text="Не работает <VPN> & доступ",
            requester_name="Иван <script>",
            requester_phone="89649063437",
        )

        text = render_group_ticket(ticket)

        self.assertIn("Категория: VPN &lt;Corp&gt;", text)
        self.assertIn("Пользователь: Иван &lt;script&gt;", text)
        self.assertIn("Не работает &lt;VPN&gt; &amp; доступ", text)
        self.assertIn('<a href="tel:+79649063437">+79649063437</a>', text)

    def test_render_group_ticket_includes_closing_reply_only_when_present(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="VPN",
            text="Не работает",
            status=TicketStatus.CLOSED,
        )
        service = TicketClarificationService()
        closing_reply = service.save_closing_reply(
            ticket_id="T-00001",
            actor_user_id=501,
            actor_name="Дмитрий",
            text="VPN восстановлен & проверен",
        )

        text = render_group_ticket(ticket, closing_reply=closing_reply)
        regular_text = render_group_ticket(ticket)

        self.assertIn("Ответ при закрытии:", text)
        self.assertIn("VPN восстановлен &amp; проверен", text)
        self.assertNotIn("Ответ при закрытии:", regular_text)

    def test_render_group_ticket_includes_room_ticket_context(self) -> None:
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="Интернет",
            text="Не работает Wi-Fi",
        )
        context = RoomTicketContext(
            ticket_key="T-00001",
            hotel_id=1,
            location_id=2,
            issue_category_id=3,
            room_number_snapshot="2105",
            location_display_snapshot="Корпус <2>, номер 2105",
            category_snapshot="Интернет & Wi-Fi",
        )

        text = render_group_ticket(ticket, room_context=context)

        self.assertIn("Объект:", text)
        self.assertIn("Корпус &lt;2&gt;, номер 2105", text)
        self.assertIn("Категория объекта:", text)
        self.assertIn("Интернет &amp; Wi-Fi", text)

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
