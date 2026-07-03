import unittest

from maxapi.enums.parse_mode import ParseMode

from app.bot.services.max_message_service import MaxMessageService


class FakeCallbackEvent:
    def __init__(self) -> None:
        self.answer_calls = []

    async def answer(self, **kwargs):
        self.answer_calls.append(kwargs)
        return object()


class FakeBot:
    def __init__(self) -> None:
        self.deleted_ids = []

    async def delete_message(self, *, message_id: str):
        self.deleted_ids.append(message_id)


class MaxMessageServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_callback_with_message_passes_new_attachments(self) -> None:
        event = FakeCallbackEvent()
        attachment = object()
        service = MaxMessageService()

        ok = await service.answer_callback_with_message(
            event=event,
            text="updated",
            attachments=[attachment],
            notification="done",
            text_format=ParseMode.HTML,
            notify=False,
        )

        self.assertTrue(ok)
        self.assertEqual(event.answer_calls[0]["new_text"], "updated")
        self.assertEqual(event.answer_calls[0]["attachments"], [attachment])
        self.assertEqual(event.answer_calls[0]["notification"], "done")
        self.assertEqual(event.answer_calls[0]["format"], ParseMode.HTML)
        self.assertFalse(event.answer_calls[0]["notify"])

    async def test_delete_message_calls_bot_delete(self) -> None:
        bot = FakeBot()
        service = MaxMessageService()

        ok = await service.delete_message(bot=bot, message_id="mid-1")

        self.assertTrue(ok)
        self.assertEqual(bot.deleted_ids, ["mid-1"])


if __name__ == "__main__":
    unittest.main()
