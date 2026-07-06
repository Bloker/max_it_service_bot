"""Тесты adapter-а webhook update -> maxapi Dispatcher."""

import unittest
from unittest.mock import AsyncMock, patch

from app.bot.webhook_server import MaxWebhookUpdateAdapter


class _FakeDispatcher:
    def __init__(self) -> None:
        self.startup = AsyncMock()
        self.handle = AsyncMock()


class _FakeBot:
    pass


class _FakeEvent:
    update_type = "bot_started"


class WebhookUpdateAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_delegates_to_dispatcher(self) -> None:
        dispatcher = _FakeDispatcher()
        bot = _FakeBot()
        adapter = MaxWebhookUpdateAdapter(dispatcher=dispatcher, bot=bot)

        await adapter.startup()

        dispatcher.startup.assert_awaited_once_with(bot)

    async def test_process_dispatches_known_update(self) -> None:
        dispatcher = _FakeDispatcher()
        bot = _FakeBot()
        adapter = MaxWebhookUpdateAdapter(dispatcher=dispatcher, bot=bot)
        event = _FakeEvent()

        with patch(
            "app.bot.webhook_server.process_update_webhook",
            new=AsyncMock(return_value=event),
        ) as process_update:
            accepted = await adapter.process({"update_type": "bot_started"})

        self.assertTrue(accepted)
        process_update.assert_awaited_once_with(
            event_json={"update_type": "bot_started"},
            bot=bot,
        )
        dispatcher.handle.assert_awaited_once_with(event)

    async def test_process_ignores_unknown_update(self) -> None:
        dispatcher = _FakeDispatcher()
        adapter = MaxWebhookUpdateAdapter(dispatcher=dispatcher, bot=_FakeBot())

        with patch(
            "app.bot.webhook_server.process_update_webhook",
            new=AsyncMock(return_value=None),
        ):
            accepted = await adapter.process({"update_type": "new_unknown"})

        self.assertFalse(accepted)
        dispatcher.handle.assert_not_awaited()

    async def test_process_normalizes_voice_attachment_before_validation(self) -> None:
        dispatcher = _FakeDispatcher()
        adapter = MaxWebhookUpdateAdapter(dispatcher=dispatcher, bot=_FakeBot())
        payload = {
            "update_type": "message_created",
            "message": {
                "body": {
                    "attachments": [
                        {"type": "voice", "payload": {"token": "hidden"}},
                    ],
                },
            },
        }

        with patch(
            "app.bot.webhook_server.process_update_webhook",
            new=AsyncMock(return_value=_FakeEvent()),
        ) as process_update:
            await adapter.process(payload)

        event_json = process_update.await_args.kwargs["event_json"]
        attachment = event_json["message"]["body"]["attachments"][0]
        self.assertEqual(attachment["type"], "audio")


if __name__ == "__main__":
    unittest.main()
