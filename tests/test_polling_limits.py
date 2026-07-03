import unittest

from app.bot.bot import configure_long_polling_limits, _normalize_voice_attachments
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


class NormalizeVoiceAttachmentsTests(unittest.TestCase):
    def test_normalizes_voice_type_to_audio(self) -> None:
        events = {
            "updates": [
                {
                    "update_type": "message_created",
                    "message": {
                        "body": {
                            "attachments": [
                                {"type": "voice", "payload": {"token": "abc"}},
                            ],
                        },
                    },
                },
            ],
        }
        result = _normalize_voice_attachments(events)
        att = result["updates"][0]["message"]["body"]["attachments"][0]
        self.assertEqual("audio", att["type"])

    def test_normalizes_multiple_voice_variants(self) -> None:
        events = {
            "updates": [
                {
                    "update_type": "message_created",
                    "message": {
                        "body": {
                            "attachments": [
                                {"type": "voice_message", "payload": {"token": "a"}},
                                {"type": "audiomsg", "payload": {"token": "b"}},
                                {"type": "audio_message", "payload": {"token": "c"}},
                                {"type": "ptt", "payload": {"token": "d"}},
                            ],
                        },
                    },
                },
            ],
        }
        result = _normalize_voice_attachments(events)
        attachments = result["updates"][0]["message"]["body"]["attachments"]
        for att in attachments:
            self.assertEqual("audio", att["type"])

    def test_preserves_existing_audio_type(self) -> None:
        events = {
            "updates": [
                {
                    "update_type": "message_created",
                    "message": {
                        "body": {
                            "attachments": [
                                {"type": "audio", "payload": {"token": "abc"}},
                            ],
                        },
                    },
                },
            ],
        }
        result = _normalize_voice_attachments(events)
        att = result["updates"][0]["message"]["body"]["attachments"][0]
        self.assertEqual("audio", att["type"])

    def test_preserves_non_audio_attachments(self) -> None:
        events = {
            "updates": [
                {
                    "update_type": "message_created",
                    "message": {
                        "body": {
                            "attachments": [
                                {"type": "image", "payload": {"token": "img"}},
                                {"type": "file", "payload": {"token": "f"}},
                            ],
                        },
                    },
                },
            ],
        }
        result = _normalize_voice_attachments(events)
        attachments = result["updates"][0]["message"]["body"]["attachments"]
        self.assertEqual("image", attachments[0]["type"])
        self.assertEqual("file", attachments[1]["type"])

    def test_handles_missing_body_or_attachments(self) -> None:
        events = {
            "updates": [
                {"update_type": "message_created", "message": {}},
                {"update_type": "message_created", "message": {"body": None}},
                {"update_type": "message_created", "message": {"body": {}}},
                {"update_type": "bot_started", "message": None},
            ],
        }
        result = _normalize_voice_attachments(events)
        self.assertEqual(4, len(result["updates"]))

    def test_logs_message_created_without_message_payload(self) -> None:
        events = {
            "updates": [
                {
                    "update_type": "message_created",
                    "timestamp": 1782997197166,
                    "user_locale": "ru",
                },
            ],
        }

        with self.assertLogs("app.bot.bot", level="WARNING") as captured:
            result = _normalize_voice_attachments(events)

        self.assertIs(result, events)
        self.assertTrue(any(
            "MAX API did not provide message/mid" in line
            for line in captured.output
        ))

    def test_returns_none_for_none_input(self) -> None:
        self.assertIsNone(_normalize_voice_attachments(None))


if __name__ == "__main__":
    unittest.main()
