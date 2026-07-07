import unittest

from maxapi.exceptions import MaxApiError
from maxapi.enums.parse_mode import ParseMode

from app.bot.services.max_api_retry import MaxApiRetryConfig
from app.bot.services.max_message_service import MaxMessageService


class FakeCallbackEvent:
    def __init__(self) -> None:
        self.answer_calls = []
        self.message = _Message("callback-mid")

    async def answer(self, **kwargs):
        self.answer_calls.append(kwargs)
        return object()


class FakeBot:
    def __init__(self) -> None:
        self.deleted_ids = []
        self.edit_calls = []
        self.send_calls = []
        self.send_failures: list[Exception] = []
        self.edit_failures: list[Exception] = []

    async def delete_message(self, *, message_id: str):
        self.deleted_ids.append(message_id)

    async def edit_message(self, **kwargs):
        self.edit_calls.append(kwargs)
        if self.edit_failures:
            raise self.edit_failures.pop(0)
        return object()

    async def send_message(self, **kwargs):
        self.send_calls.append(kwargs)
        if self.send_failures:
            raise self.send_failures.pop(0)
        return _SentMessage("sent-mid")


class _Body:
    def __init__(self, mid: str) -> None:
        self.mid = mid


class _Message:
    def __init__(self, mid: str) -> None:
        self.body = _Body(mid)


class _SentMessage:
    def __init__(self, mid: str) -> None:
        self.message = _Message(mid)


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

    async def test_send_message_retries_explicit_429_then_success(self) -> None:
        bot = FakeBot()
        bot.send_failures = [MaxApiError(429, {"error": "too.many.requests"})]
        sleeps: list[float] = []
        service = MaxMessageService(
            retry_config=MaxApiRetryConfig(max_attempts=3, jitter_sec=0.0),
            sleep=_fake_sleep(sleeps),
        )

        mid = await service.send_message(bot=bot, chat_id=-100, text="test")

        self.assertEqual(mid, "sent-mid")
        self.assertEqual(len(bot.send_calls), 2)
        self.assertEqual(sleeps, [0.5])

    async def test_send_message_does_not_retry_permanent_error(self) -> None:
        bot = FakeBot()
        bot.send_failures = [MaxApiError(400, {"message": "bad payload"})]
        service = MaxMessageService()

        mid = await service.send_message(bot=bot, chat_id=-100, text="test")

        self.assertIsNone(mid)
        self.assertEqual(len(bot.send_calls), 1)

    async def test_edit_message_rate_limiter_waits_for_same_message(self) -> None:
        bot = FakeBot()
        sleeps: list[float] = []
        now = _FakeClock()
        service = MaxMessageService(
            retry_config=MaxApiRetryConfig(edit_min_interval_sec=1.0),
            sleep=_fake_sleep(sleeps),
            monotonic=now,
        )

        self.assertTrue(await service.edit_message(bot=bot, message_id="mid-1", text="one"))
        now.value = 0.25
        self.assertTrue(await service.edit_message(bot=bot, message_id="mid-1", text="two"))

        self.assertEqual(len(bot.edit_calls), 2)
        self.assertEqual(sleeps, [0.75])

    async def test_edit_message_rate_limiter_does_not_wait_for_different_message(self) -> None:
        bot = FakeBot()
        sleeps: list[float] = []
        now = _FakeClock()
        service = MaxMessageService(
            retry_config=MaxApiRetryConfig(edit_min_interval_sec=1.0),
            sleep=_fake_sleep(sleeps),
            monotonic=now,
        )

        self.assertTrue(await service.edit_message(bot=bot, message_id="mid-1", text="one"))
        now.value = 0.25
        self.assertTrue(await service.edit_message(bot=bot, message_id="mid-2", text="two"))

        self.assertEqual(sleeps, [])

    async def test_callback_message_update_uses_same_edit_rate_limiter(self) -> None:
        event = FakeCallbackEvent()
        sleeps: list[float] = []
        now = _FakeClock()
        service = MaxMessageService(
            retry_config=MaxApiRetryConfig(edit_min_interval_sec=1.0),
            sleep=_fake_sleep(sleeps),
            monotonic=now,
        )

        self.assertTrue(await service.answer_callback_with_message(event=event, text="one"))
        now.value = 0.4
        self.assertTrue(await service.answer_callback_with_message(event=event, text="two"))

        self.assertEqual(sleeps, [0.6])
        self.assertEqual(len(event.answer_calls), 2)


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _fake_sleep(calls: list[float]):
    async def sleep(delay: float) -> None:
        calls.append(round(delay, 3))

    return sleep


if __name__ == "__main__":
    unittest.main()
