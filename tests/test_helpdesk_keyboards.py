import unittest

from app.helpdesk.keyboards.helpdesk_keyboards import build_open_tickets_keyboard
from app.helpdesk.models.ticket import Ticket


class HelpdeskKeyboardTests(unittest.TestCase):
    def test_open_tickets_keyboard_adds_ticket_buttons_and_refresh(self) -> None:
        tickets = [
            Ticket(id="T-00001", user_id=101, category="Доступ", text="One"),
            Ticket(id="T-00002", user_id=102, category="Wi-Fi", text="Two"),
            Ticket(id="T-00003", user_id=103, category="Прочее", text="Three"),
        ]

        keyboard = build_open_tickets_keyboard(tickets)

        buttons = keyboard.payload.buttons
        self.assertEqual([button.text for button in buttons[0]], ["T-00001", "T-00002"])
        self.assertEqual([button.payload for button in buttons[0]], [
            "spc|open_card|T-00001",
            "spc|open_card|T-00002",
        ])
        self.assertEqual(buttons[1][0].text, "T-00003")
        self.assertEqual(buttons[1][0].payload, "spc|open_card|T-00003")
        self.assertEqual(buttons[-1][0].text, "Обновить список")
        self.assertEqual(buttons[-1][0].payload, "spc|open_list|-")


if __name__ == "__main__":
    unittest.main()
