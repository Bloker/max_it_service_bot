"""Проверки пользовательских уведомлений по заявкам."""

import unittest

from maxapi.enums.parse_mode import ParseMode

from app.bot.notifications import notify_user_ticket_closed, notify_user_ticket_submitted
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket


class FakeBot:
    """Сохраняет вызовы отправки сообщений для проверки уведомления."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeMaxMessages:
    """Сохраняет последовательность безопасных отправок через MAX API service."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"mid-{len(self.calls)}"


class NotificationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_submitted_ticket_sends_confirmation_then_card_without_menu(self) -> None:
        bot = FakeBot()
        max_messages = FakeMaxMessages()
        ticket = Ticket(id="T-00011", user_id=42, category="Интернет", text="Нет сети")
        user_message_id = await notify_user_ticket_submitted(
            bot=bot,
            max_messages=max_messages,
            ticket=ticket,
            media_attachments=["photo", "video"],
        )

        self.assertEqual(user_message_id, "mid-2")
        self.assertEqual(len(max_messages.calls), 2)
        self.assertEqual(
            max_messages.calls[0]["text"],
            "Заявка принята и передана специалистам.",
        )
        self.assertIn("<b>Заявка T-00011</b>", max_messages.calls[1]["text"])
        self.assertIn("Нет сети", max_messages.calls[1]["text"])
        self.assertEqual(max_messages.calls[1]["attachments"][:2], ["photo", "video"])
        buttons = max_messages.calls[1]["attachments"][-1].payload.buttons
        self.assertEqual(
            [button.text for row in buttons for button in row],
            ["➕ Дополнить заявку", "← Мои обращения", "Главное меню"],
        )
        self.assertEqual(max_messages.calls[1]["text_format"], ParseMode.HTML)

    async def test_submitted_room_ticket_card_contains_object(self) -> None:
        max_messages = FakeMaxMessages()
        ticket = Ticket(id="T-00012", user_id=42, category="ТВ", text="Нет сигнала")
        context = RoomTicketContext(
            ticket_key=ticket.ticket_id,
            hotel_id=1,
            location_id=112,
            room_number_snapshot="112",
            location_display_snapshot="Джамайка · 1 корпус · номер 112",
            category_snapshot="ТВ",
        )

        await notify_user_ticket_submitted(
            bot=FakeBot(),
            max_messages=max_messages,
            ticket=ticket,
            room_context=context,
        )

        self.assertIn("Объект: Номер 112 (ТВ)", max_messages.calls[1]["text"])

    async def test_closed_ticket_notification_has_main_menu_button(self) -> None:
        bot = FakeBot()
        ticket = Ticket(id="T-00010", user_id=42, category="ТВ", text="Нет сигнала")

        delivered = await notify_user_ticket_closed(bot, ticket)

        self.assertTrue(delivered)
        self.assertEqual(bot.calls[0]["text"], "Заявка T-00010 выполнена.")
        keyboard = bot.calls[0]["attachments"][0]
        self.assertEqual(keyboard.payload.buttons[0][0].text, "Главное меню")
        self.assertEqual(keyboard.payload.buttons[0][0].payload, "usr|menu|")


if __name__ == "__main__":
    unittest.main()
