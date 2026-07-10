"""Проверки пользовательских уведомлений о закрытии заявки."""

import unittest

from app.bot.notifications import notify_user_ticket_closed
from app.helpdesk.models.ticket import Ticket


class FakeBot:
    """Сохраняет вызовы отправки сообщений для проверки уведомления."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.calls.append(kwargs)


class NotificationsTests(unittest.IsolatedAsyncioTestCase):
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
