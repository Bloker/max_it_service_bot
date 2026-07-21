"""Тесты aiohttp webhook server."""

import unittest
from asyncio import Event, create_task

from app.bot.webhook_server import (
    UPDATE_PROCESSOR_KEY,
    WEBHOOK_SECRET_KEY,
    WebhookUpdateDeduplicator,
    create_webhook_app,
    handle_health,
    handle_webhook,
)
from config.config import BotConfig


def _bot_config(*, secret: str = "") -> BotConfig:
    """Создает минимальный BotConfig для тестов webhook server."""

    return BotConfig(
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
        update_mode="webhook",
        webhook_host="127.0.0.1",
        webhook_port=8080,
        webhook_path="/max-webhook",
        webhook_health_path="/health",
        webhook_secret=secret,
    )


class WebhookUpdateDeduplicatorTests(unittest.TestCase):
    def test_key_can_be_reused_after_ttl(self) -> None:
        current_time = 10.0
        deduplicator = WebhookUpdateDeduplicator(
            ttl_seconds=5.0,
            clock=lambda: current_time,
        )

        self.assertTrue(deduplicator.acquire("message_created:mid-1"))
        self.assertFalse(deduplicator.acquire("message_created:mid-1"))
        current_time = 15.0
        self.assertTrue(deduplicator.acquire("message_created:mid-1"))

    def test_capacity_evicts_oldest_key(self) -> None:
        deduplicator = WebhookUpdateDeduplicator(max_entries=2)

        self.assertTrue(deduplicator.acquire("message_created:mid-1"))
        self.assertTrue(deduplicator.acquire("message_created:mid-2"))
        self.assertTrue(deduplicator.acquire("message_created:mid-3"))
        self.assertTrue(deduplicator.acquire("message_created:mid-1"))


class WebhookServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.processed_payloads = []

    def _make_app(self, cfg: BotConfig):
        async def processor(payload):
            self.processed_payloads.append(payload)
            return True

        return create_webhook_app(
            cfg=cfg,
            update_processor=processor,
            startup_handler=None,
        )

    @staticmethod
    def _request(app, *, headers=None, payload=None, json_error: Exception | None = None):
        class _Request:
            def __init__(self):
                self.app = app
                self.headers = headers or {}

            async def json(self):
                if json_error is not None:
                    raise json_error
                return payload

        return _Request()

    async def test_health_returns_safe_payload(self) -> None:
        app = self._make_app(_bot_config(secret="hidden-secret"))

        response = await handle_health(self._request(app))

        self.assertEqual(response.status, 200)
        self.assertIn('"status": "ok"', response.text)
        self.assertIn('"mode": "webhook"', response.text)
        self.assertNotIn("hidden-secret", response.text)
        self.assertNotIn("token", response.text.lower())

    async def test_missing_secret_is_forbidden_when_secret_configured(self) -> None:
        app = self._make_app(_bot_config(secret="expected"))

        response = await handle_webhook(
            self._request(app, payload={"update_type": "bot_started"})
        )

        self.assertEqual(response.status, 403)
        self.assertEqual(self.processed_payloads, [])

    async def test_wrong_secret_is_forbidden(self) -> None:
        app = self._make_app(_bot_config(secret="expected"))

        response = await handle_webhook(self._request(
            app,
            headers={"X-Max-Bot-Api-Secret": "wrong"},
            payload={"update_type": "bot_started"},
        ))

        self.assertEqual(response.status, 403)
        self.assertEqual(self.processed_payloads, [])

    async def test_correct_secret_allows_processing(self) -> None:
        app = self._make_app(_bot_config(secret="expected"))

        response = await handle_webhook(self._request(
            app,
            headers={"X-Max-Bot-Api-Secret": "expected"},
            payload={"update_type": "bot_started"},
        ))

        self.assertEqual(response.status, 200)
        self.assertEqual(self.processed_payloads, [{"update_type": "bot_started"}])

    async def test_empty_body_is_bad_request(self) -> None:
        app = self._make_app(_bot_config())

        response = await handle_webhook(self._request(app, payload={}))

        self.assertEqual(response.status, 400)

    async def test_invalid_json_is_bad_request(self) -> None:
        app = self._make_app(_bot_config())

        response = await handle_webhook(
            self._request(app, json_error=ValueError("bad json"))
        )

        self.assertEqual(response.status, 400)

    async def test_no_secret_allows_unsigned_dev_request(self) -> None:
        app = self._make_app(_bot_config(secret=""))

        response = await handle_webhook(
            self._request(app, payload={"update_type": "bot_started"})
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(len(self.processed_payloads), 1)

    async def test_processing_exception_returns_controlled_200(self) -> None:
        async def broken_processor(payload):
            raise RuntimeError("handler failed")

        cfg = _bot_config(secret="")
        app = create_webhook_app(
            cfg=cfg,
            update_processor=broken_processor,
            startup_handler=None,
        )

        response = await handle_webhook(
            self._request(app, payload={"update_type": "bot_started"})
        )

        self.assertEqual(response.status, 200)
        self.assertIn("processing_failed", response.text)

    async def test_duplicate_message_is_processed_once(self) -> None:
        app = self._make_app(_bot_config())
        payload = {
            "update_type": "message_created",
            "message": {"body": {"mid": "mid-1"}},
        }

        first = await handle_webhook(self._request(app, payload=payload))
        duplicate = await handle_webhook(self._request(app, payload=payload))

        self.assertEqual(first.status, 200)
        self.assertEqual(duplicate.status, 200)
        self.assertIn('"duplicate": true', duplicate.text)
        self.assertEqual(self.processed_payloads, [payload])

    async def test_concurrent_duplicate_is_not_dispatched(self) -> None:
        processing_started = Event()
        allow_processing = Event()
        processed_payloads = []

        async def slow_processor(payload):
            processed_payloads.append(payload)
            processing_started.set()
            await allow_processing.wait()
            return True

        app = create_webhook_app(
            cfg=_bot_config(),
            update_processor=slow_processor,
            startup_handler=None,
        )
        payload = {
            "update_type": "message_created",
            "message": {"body": {"mid": "mid-slow"}},
        }

        first_task = create_task(handle_webhook(self._request(app, payload=payload)))
        await processing_started.wait()
        duplicate = await handle_webhook(self._request(app, payload=payload))
        allow_processing.set()
        first = await first_task

        self.assertEqual(first.status, 200)
        self.assertIn('"duplicate": true', duplicate.text)
        self.assertEqual(processed_payloads, [payload])

    async def test_different_message_ids_are_processed(self) -> None:
        app = self._make_app(_bot_config())

        for mid in ("mid-1", "mid-2"):
            response = await handle_webhook(self._request(
                app,
                payload={
                    "update_type": "message_created",
                    "message": {"body": {"mid": mid}},
                },
            ))
            self.assertEqual(response.status, 200)

        self.assertEqual(len(self.processed_payloads), 2)

    async def test_message_without_mid_is_not_deduplicated(self) -> None:
        app = self._make_app(_bot_config())
        payload = {
            "update_type": "message_created",
            "message": {"body": {}},
        }

        await handle_webhook(self._request(app, payload=payload))
        await handle_webhook(self._request(app, payload=payload))

        self.assertEqual(self.processed_payloads, [payload, payload])

    async def test_processing_error_releases_message_id(self) -> None:
        attempts = 0

        async def processor(payload):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary failure")
            return True

        app = create_webhook_app(
            cfg=_bot_config(),
            update_processor=processor,
            startup_handler=None,
        )
        payload = {
            "update_type": "message_created",
            "message": {"body": {"mid": "mid-retry"}},
        }

        failed = await handle_webhook(self._request(app, payload=payload))
        retried = await handle_webhook(self._request(app, payload=payload))

        self.assertIn("processing_failed", failed.text)
        self.assertEqual(retried.status, 200)
        self.assertEqual(attempts, 2)

    def test_app_stores_secret_and_processor_without_routes_side_effects(self) -> None:
        app = self._make_app(_bot_config(secret="expected"))

        self.assertEqual(app[WEBHOOK_SECRET_KEY], "expected")
        self.assertTrue(callable(app[UPDATE_PROCESSOR_KEY]))


if __name__ == "__main__":
    unittest.main()
