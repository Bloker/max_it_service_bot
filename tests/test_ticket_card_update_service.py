import unittest

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.services.ticket_internal_comment_service import (
    TicketInternalComment,
    TicketInternalCommentService,
)
from app.helpdesk.services.ticket_card_update_service import TicketCardUpdateService
from app.helpdesk.services.ticket_clarification_service import TicketClarificationService
from app.helpdesk.services.ticket_link_service import TicketLinkService


class FakeMaxMessages:
    def __init__(
        self,
        *,
        edit_result: bool = True,
        send_result: str | None = "new-mid",
    ) -> None:
        self.edit_result = edit_result
        self.send_result = send_result
        self.edit_calls = []
        self.send_calls = []
        self.callback_update_calls = []
        self.callback_answer_calls = []

    async def edit_message(self, **kwargs) -> bool:
        self.edit_calls.append(kwargs)
        return self.edit_result

    async def send_message(self, **kwargs) -> str | None:
        self.send_calls.append(kwargs)
        return self.send_result

    async def answer_callback_with_message(self, **kwargs) -> bool:
        self.callback_update_calls.append(kwargs)
        return True

    async def answer_callback(self, **kwargs) -> bool:
        self.callback_answer_calls.append(kwargs)
        return True


class FakeMessageBody:
    mid = "callback-mid"


class FakeMessage:
    body = FakeMessageBody()


class FakeEvent:
    message = FakeMessage()

    def _ensure_bot(self):
        return object()


class FakeRoomContexts:
    def __init__(self, context: RoomTicketContext | None = None) -> None:
        self.context = context

    def get_context(self, ticket_id: str) -> RoomTicketContext | None:
        return self.context


class FakeInternalComments(TicketInternalCommentService):
    def __init__(self, comment: TicketInternalComment | None = None) -> None:
        super().__init__()
        self.comment = comment

    def get_last(self, ticket_id: str):
        return self.comment


class TicketCardUpdateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_updates_existing_group_card_in_place(self) -> None:
        links = TicketLinkService()
        links.bind_group_message("T-00001", "root-mid", primary=True)
        max_messages = FakeMaxMessages(edit_result=True)
        service = TicketCardUpdateService(
            ticket_links=links,
            group_chat_id=-100,
            max_messages=max_messages,
        )
        ticket = Ticket(
            id="T-00001",
            user_id=101,
            category="Доступ",
            text="Test",
            status=TicketStatus.IN_PROGRESS,
            assignee_name="Spec",
        )

        updated = await service.update_group_ticket_card(bot=object(), ticket=ticket)

        self.assertTrue(updated)
        self.assertEqual(max_messages.edit_calls[0]["message_id"], "root-mid")
        self.assertIn("Статус: <b>в работе</b>", max_messages.edit_calls[0]["text"])
        self.assertEqual(max_messages.send_calls, [])
        self.assertEqual(links.get_group_message_id("T-00001"), "root-mid")

    async def test_sends_reply_fallback_and_rebinds_primary_when_edit_fails(self) -> None:
        links = TicketLinkService()
        links.bind_group_message("T-00002", "root-mid", primary=True)
        max_messages = FakeMaxMessages(edit_result=False, send_result="fallback-mid")
        service = TicketCardUpdateService(
            ticket_links=links,
            group_chat_id=-100,
            max_messages=max_messages,
        )
        ticket = Ticket(
            id="T-00002",
            user_id=102,
            category="Wi-Fi",
            text="Test",
            status=TicketStatus.WAITING_USER,
        )

        updated = await service.update_group_ticket_card(bot=object(), ticket=ticket)

        self.assertTrue(updated)
        self.assertEqual(max_messages.send_calls[0]["reply_to_message_id"], "root-mid")
        self.assertEqual(links.get_group_message_id("T-00002"), "fallback-mid")

    async def test_sends_new_primary_card_when_link_is_missing(self) -> None:
        links = TicketLinkService()
        max_messages = FakeMaxMessages(edit_result=True, send_result="new-primary-mid")
        service = TicketCardUpdateService(
            ticket_links=links,
            group_chat_id=-100,
            max_messages=max_messages,
        )
        ticket = Ticket(id="T-00003", user_id=103, category="Прочее", text="Test")

        updated = await service.update_group_ticket_card(bot=object(), ticket=ticket)

        self.assertTrue(updated)
        self.assertEqual(max_messages.edit_calls, [])
        self.assertEqual(max_messages.send_calls[0]["chat_id"], -100)
        self.assertEqual(links.get_group_message_id("T-00003"), "new-primary-mid")

    async def test_updates_clicked_card_with_callback_message_and_rebinds_primary(self) -> None:
        links = TicketLinkService()
        links.bind_group_message("T-00004", "old-primary", primary=True)
        max_messages = FakeMaxMessages()
        room_contexts = FakeRoomContexts(
            RoomTicketContext(ticket_key="T-00004", hotel_id=1, location_id=12)
        )
        service = TicketCardUpdateService(
            ticket_links=links,
            group_chat_id=-100,
            max_messages=max_messages,
            room_contexts=room_contexts,
        )
        ticket = Ticket(
            id="T-00004",
            user_id=104,
            category="Доступ",
            text="Test",
            status=TicketStatus.IN_PROGRESS,
        )

        updated = await service.update_group_ticket_card_from_callback(
            event=FakeEvent(),
            ticket=ticket,
            notification="Заявка назначена на вас",
        )

        self.assertTrue(updated)
        call = max_messages.callback_update_calls[0]
        self.assertEqual(call["notification"], "Заявка назначена на вас")
        self.assertIn("Статус: <b>в работе</b>", call["text"])
        self.assertEqual(call["attachments"][0].payload.buttons[0][0].text, "Освободить")
        self.assertEqual(
            [button.text for button in call["attachments"][0].payload.buttons[-2]],
            ["История номера"],
        )
        self.assertEqual(links.get_group_message_id("T-00004"), "callback-mid")

    async def test_updates_card_with_attached_user_reply_media_before_keyboard(self) -> None:
        links = TicketLinkService()
        links.bind_group_message("T-00005", "root-mid", primary=True)
        clarifications = TicketClarificationService()
        clarifications.set_ticket_base_attachments(
            ticket_id="T-00005",
            attachments=["initial-photo"],
        )
        clarifications.save_last(
            ticket_id="T-00005",
            actor_user_id=501,
            actor_name="Spec",
            text="[вложение]",
            attachments=["clarification-photo"],
        )
        clarifications.save_user_reply_candidate(
            ticket_id="T-00005",
            user_id=105,
            user_name="User",
            text="[вложение]",
            group_message_id="reply-mid",
            attachments=["photo-attachment"],
        )
        clarifications.attach_user_reply("reply-mid")
        max_messages = FakeMaxMessages(edit_result=True)
        service = TicketCardUpdateService(
            ticket_links=links,
            group_chat_id=-100,
            max_messages=max_messages,
            clarifications=clarifications,
        )
        ticket = Ticket(
            id="T-00005",
            user_id=105,
            category="Wi-Fi",
            text="Test",
            status=TicketStatus.WAITING_USER,
        )

        updated = await service.update_group_ticket_card(bot=object(), ticket=ticket)

        self.assertTrue(updated)
        attachments = max_messages.edit_calls[0]["attachments"]
        self.assertEqual(attachments[0], "initial-photo")
        self.assertEqual(attachments[1], "clarification-photo")
        self.assertEqual(attachments[2], "photo-attachment")
        self.assertEqual(attachments[3].payload.buttons[0][0].text, "Взять в работу")
        self.assertIn("Ответ пользователя:", max_messages.edit_calls[0]["text"])

    async def test_updates_card_with_last_internal_comment_block(self) -> None:
        links = TicketLinkService()
        links.bind_group_message("T-00006", "root-mid", primary=True)
        max_messages = FakeMaxMessages(edit_result=True)
        comment = TicketInternalComment(
            ticket_id="T-00006",
            body="Проверен порт коммутатора",
            created_at=None,
        )
        service = TicketCardUpdateService(
            ticket_links=links,
            group_chat_id=-100,
            max_messages=max_messages,
            internal_comments=FakeInternalComments(comment),
        )
        ticket = Ticket(id="T-00006", user_id=101, category="Интернет", text="Нет сети")

        updated = await service.update_group_ticket_card(bot=object(), ticket=ticket)

        self.assertTrue(updated)
        self.assertIn("Внутренний комментарий:", max_messages.edit_calls[0]["text"])
        self.assertIn("Проверен порт коммутатора", max_messages.edit_calls[0]["text"])


if __name__ == "__main__":
    unittest.main()
