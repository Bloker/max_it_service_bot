import unittest

from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_attach_user_reply_keyboard,
    build_categories_keyboard,
    build_clarification_cancel_keyboard,
    build_clarification_reply_keyboard,
    build_close_reply_cancel_keyboard,
    build_jamaica_issue_categories_keyboard,
    build_jamaica_cancel_keyboard,
    build_jamaica_main_menu_keyboard,
    build_jamaica_room_not_found_keyboard,
    build_main_menu_keyboard,
    build_open_tickets_keyboard,
    build_ticket_actions_keyboard,
)
from app.helpdesk.repositories.location_repository import IssueCategoryRef
from app.helpdesk.models.ticket import Ticket, TicketStatus


class HelpdeskKeyboardTests(unittest.TestCase):
    def test_main_menu_starts_with_create_ticket_for_regular_user(self) -> None:
        keyboard = build_main_menu_keyboard(
            can_create_ticket=True,
            can_view_my_tickets=True,
            can_view_help=True,
            can_view_about=False,
            can_use_network_tools=False,
            is_admin=False,
        )

        buttons = keyboard.payload.buttons
        self.assertEqual(buttons[0][0].text, "Создать обращение")
        self.assertEqual(buttons[0][0].payload, "usr|create|")
        self.assertEqual(buttons[1][0].text, "Мои обращения")
        all_labels = [button.text for row in buttons for button in row]
        self.assertNotIn("Сетевые инструменты", all_labels)
        self.assertNotIn("Права администратора", all_labels)

    def test_main_menu_keeps_service_buttons_for_it_and_admin(self) -> None:
        keyboard = build_main_menu_keyboard(
            can_create_ticket=True,
            can_view_my_tickets=True,
            can_view_help=False,
            can_use_network_tools=True,
            is_admin=True,
        )

        all_labels = [button.text for row in keyboard.payload.buttons for button in row]
        self.assertEqual(keyboard.payload.buttons[0][0].text, "Создать обращение")
        self.assertIn("Сетевые инструменты", all_labels)
        self.assertIn("Права администратора", all_labels)

    def test_categories_keyboard_has_main_menu_button(self) -> None:
        keyboard = build_categories_keyboard(["Доступы"])

        button = keyboard.payload.buttons[-1][0]
        self.assertEqual(button.text, "Главное меню")
        self.assertEqual(button.payload, "usr|menu|")

    def test_jamaica_main_menu_has_room_other_my_help_without_buildings(self) -> None:
        keyboard = build_jamaica_main_menu_keyboard()

        labels = [button.text for row in keyboard.payload.buttons for button in row]
        self.assertEqual(
            labels,
            ["Заявка по номеру", "Прочее", "Мои заявки", "Помощь"],
        )
        self.assertNotIn("Корпус", " ".join(labels))
        self.assertNotIn("Здание", " ".join(labels))

    def test_jamaica_issue_categories_keyboard_uses_category_code_payload(self) -> None:
        keyboard = build_jamaica_issue_categories_keyboard(
            (
                IssueCategoryRef(1, "tv", "ТВ", True, 10),
                IssueCategoryRef(2, "other", "Прочее", False, 50),
            )
        )

        self.assertEqual(keyboard.payload.buttons[0][0].text, "ТВ")
        self.assertEqual(keyboard.payload.buttons[0][0].payload, "usr|jamaica_cat|tv")
        self.assertEqual(keyboard.payload.buttons[1][0].text, "Прочее")
        self.assertEqual(keyboard.payload.buttons[1][0].payload, "usr|jamaica_cat|other")
        self.assertEqual(len(keyboard.payload.buttons), 2)

    def test_jamaica_room_not_found_keyboard_allows_retry_other_and_menu(self) -> None:
        keyboard = build_jamaica_room_not_found_keyboard()

        labels = [row[0].text for row in keyboard.payload.buttons]
        payloads = [row[0].payload for row in keyboard.payload.buttons]
        self.assertEqual(labels, ["Ввести заново", "Создать как Прочее", "Главное меню"])
        self.assertEqual(
            payloads,
            ["usr|jamaica_room_retry|", "usr|jamaica_other|", "usr|menu|"],
        )

    def test_jamaica_cancel_keyboard_has_only_cancel_button(self) -> None:
        keyboard = build_jamaica_cancel_keyboard()

        buttons = keyboard.payload.buttons
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0][0].text, "Отмена")
        self.assertEqual(buttons[0][0].payload, "usr|jamaica_cancel|")

    def test_clarification_cancel_keyboard_contains_ticket_payload(self) -> None:
        keyboard = build_clarification_cancel_keyboard("T-00001")

        button = keyboard.payload.buttons[0][0]
        self.assertEqual(button.text, "Отмена")
        self.assertEqual(button.payload, "clc|T-00001")

    def test_clarification_reply_keyboard_contains_ticket_payload(self) -> None:
        keyboard = build_clarification_reply_keyboard("T-00001")

        button = keyboard.payload.buttons[0][0]
        self.assertEqual(button.text, "Ответить")
        self.assertEqual(button.payload, "usr|ticket_reply|T-00001")

    def test_close_reply_cancel_keyboard_contains_ticket_payload(self) -> None:
        keyboard = build_close_reply_cancel_keyboard("T-00001")

        button = keyboard.payload.buttons[0][0]
        self.assertEqual(button.text, "Отмена")
        self.assertEqual(button.payload, "crc|T-00001")

    def test_attach_user_reply_keyboard_contains_ticket_payload(self) -> None:
        keyboard = build_attach_user_reply_keyboard("T-00001")

        button = keyboard.payload.buttons[0][0]
        self.assertEqual(button.text, "Прикрепить к карточке")
        self.assertEqual(button.payload, "spc|attach_reply|T-00001")

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

    def test_ticket_actions_keyboard_for_new_ticket(self) -> None:
        ticket = Ticket(id="T-00001", user_id=101, category="Доступ", text="One")

        keyboard = build_ticket_actions_keyboard(ticket)
        buttons = keyboard.payload.buttons

        self.assertEqual(buttons[0][0].text, "Взять в работу")
        self.assertEqual(buttons[0][0].payload, "spc|take|T-00001")
        self.assertEqual(
            [button.text for button in buttons[1]],
            ["Запросить уточнение", "Закрыть"],
        )
        self.assertEqual(buttons[2][0].text, "Закрыть с ответом")
        self.assertEqual(buttons[2][0].payload, "spc|close_with_reply|T-00001")
        self.assertEqual(buttons[-1][0].text, "Не закрытые заявки")

    def test_ticket_actions_keyboard_for_in_progress_ticket(self) -> None:
        ticket = Ticket(
            id="T-00002",
            user_id=102,
            category="Wi-Fi",
            text="Two",
            status=TicketStatus.IN_PROGRESS,
        )

        keyboard = build_ticket_actions_keyboard(ticket)
        buttons = keyboard.payload.buttons

        self.assertEqual(
            [button.text for button in buttons[0]],
            ["Освободить", "Закрыть"],
        )
        self.assertEqual(buttons[1][0].text, "Закрыть с ответом")
        self.assertEqual(buttons[1][0].payload, "spc|close_with_reply|T-00002")
        self.assertEqual(buttons[2][0].text, "Запросить уточнение")
        self.assertEqual(buttons[-1][0].text, "Не закрытые заявки")

    def test_ticket_actions_keyboard_for_closed_ticket_keeps_only_safe_navigation(self) -> None:
        ticket = Ticket(
            id="T-00003",
            user_id=103,
            category="Прочее",
            text="Three",
            status=TicketStatus.CLOSED,
        )

        keyboard = build_ticket_actions_keyboard(ticket)
        buttons = keyboard.payload.buttons

        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0][0].text, "Не закрытые заявки")


if __name__ == "__main__":
    unittest.main()
