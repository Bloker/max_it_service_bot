import unittest

from app.bot.bot import configure_long_polling_limits
from config.config import BotConfig


class _FakeBot:
    def __init__(self) -> None:
        self.calls = []

    async def get_updates(self, *, limit=None, timeout=None, marker=None, types=None):
        self.calls.append(
            {
                "limit": limit,
                "timeout": timeout,
                "marker": marker,
                "types": types,
            }
        )
        return {"updates": [], "marker": marker}


class PollingLimitsTests(unittest.IsolatedAsyncioTestCase):
    async def test_configure_long_polling_limits_sets_compliant_defaults(self) -> None:
        bot = _FakeBot()
        cfg = BotConfig(
            token="token",
            group_chat_id=123,
            user_ids=(),
            user_registry_path="data/user_access_registry.json",
            admin_ids=(),
            it_specialist_ids=(),
            skip_updates_on_start=True,
            polling_limit=100,
            polling_timeout_sec=30,
            polling_min_interval_sec=0.0,
        )

        configure_long_polling_limits(bot, cfg)
        response = await bot.get_updates(marker=555)

        self.assertEqual(response, {"updates": [], "marker": 555})
        self.assertEqual(bot.calls, [
            {
                "limit": 100,
                "timeout": 30,
                "marker": 555,
                "types": None,
            }
        ])


if __name__ == "__main__":
    unittest.main()
