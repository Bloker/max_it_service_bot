"""Тесты выбора режима получения событий MAX."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot import bot as bot_module
from config.config import BotConfig


def _cfg(update_mode: str) -> SimpleNamespace:
    """Создает минимальный config object для app.bot.bot.main."""

    return SimpleNamespace(
        bot=BotConfig(
            token="token",
            group_chat_id=123,
            user_ids=(),
            user_registry_path="data/user_access_registry.json",
            admin_ids=(),
            it_specialist_ids=(),
            skip_updates_on_start=True,
            polling_limit=100,
            polling_timeout_sec=30,
            polling_min_interval_sec=0.55,
            update_mode=update_mode,
            webhook_host="127.0.0.1",
            webhook_port=8080,
            webhook_path="/max-webhook",
            webhook_health_path="/health",
            webhook_secret="secret",
        )
    )


class _FakeBot:
    instances = []

    def __init__(self, token: str) -> None:
        self.token = token
        self.delete_webhook = AsyncMock()
        self.get_updates = AsyncMock(return_value={"updates": [], "marker": None})
        _FakeBot.instances.append(self)


class _FakeDispatcher:
    instances = []

    def __init__(self) -> None:
        self.start_polling = AsyncMock()
        _FakeDispatcher.instances.append(self)


class BotUpdateModesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _FakeBot.instances.clear()
        _FakeDispatcher.instances.clear()

    async def test_longpoll_uses_polling_and_deletes_webhook(self) -> None:
        with (
            patch.object(bot_module, "get_config", return_value=_cfg("longpoll")),
            patch.object(bot_module, "Bot", _FakeBot),
            patch.object(bot_module, "Dispatcher", _FakeDispatcher),
            patch.object(bot_module, "register_routes", MagicMock()),
            patch.object(bot_module, "configure_long_polling_limits", MagicMock()),
        ):
            await bot_module.main()

        bot = _FakeBot.instances[0]
        dispatcher = _FakeDispatcher.instances[0]
        bot.delete_webhook.assert_awaited_once()
        dispatcher.start_polling.assert_awaited_once_with(bot, skip_updates=True)

    async def test_webhook_does_not_delete_subscription_or_start_polling(self) -> None:
        run_webhook = AsyncMock()
        with (
            patch.object(bot_module, "get_config", return_value=_cfg("webhook")),
            patch.object(bot_module, "Bot", _FakeBot),
            patch.object(bot_module, "Dispatcher", _FakeDispatcher),
            patch.object(bot_module, "register_routes", MagicMock()),
            patch("app.bot.webhook_server.run_webhook_server", run_webhook),
        ):
            await bot_module.main()

        bot = _FakeBot.instances[0]
        dispatcher = _FakeDispatcher.instances[0]
        bot.delete_webhook.assert_not_awaited()
        dispatcher.start_polling.assert_not_awaited()
        run_webhook.assert_awaited_once_with(
            cfg=_cfg("webhook").bot,
            dispatcher=dispatcher,
            bot=bot,
        )


if __name__ == "__main__":
    unittest.main()
