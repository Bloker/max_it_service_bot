import unittest
import json

from maxapi.exceptions import MaxApiError

from app.bot.services.max_api_retry import (
    MaxApiRetryConfig,
    MaxApiRetryExhausted,
    call_max_api_with_retry,
    classify_max_api_error,
    redact_sensitive,
)
from app.observability.services import ObservabilityService
from tests.test_observability_service import FakeObservabilityRepository


class MaxApiRetryTests(unittest.IsolatedAsyncioTestCase):
    def test_classifier_detects_429_status(self) -> None:
        info = classify_max_api_error(MaxApiError(429, {"message": "slow down"}))

        self.assertTrue(info.transient)
        self.assertTrue(info.rate_limited)
        self.assertEqual(info.status_code, 429)

    def test_classifier_detects_too_many_requests_text(self) -> None:
        info = classify_max_api_error(MaxApiError(400, {"error": "too.many.requests"}))

        self.assertTrue(info.transient)
        self.assertTrue(info.rate_limited)

    def test_classifier_detects_5xx_and_internal_error(self) -> None:
        by_status = classify_max_api_error(MaxApiError(500, {"message": "oops"}))
        by_code = classify_max_api_error(MaxApiError(400, {"error": "internal.error"}))

        self.assertTrue(by_status.transient)
        self.assertTrue(by_status.server_error)
        self.assertTrue(by_code.transient)
        self.assertTrue(by_code.server_error)

    def test_classifier_marks_4xx_as_permanent(self) -> None:
        for status in (400, 403, 404):
            info = classify_max_api_error(MaxApiError(status, {"message": "bad"}))
            self.assertFalse(info.transient)

    async def test_retry_wrapper_retries_429_then_success(self) -> None:
        calls = 0
        sleeps: list[float] = []
        repository = FakeObservabilityRepository()
        observability = ObservabilityService(repository=repository)

        async def flaky_call():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise MaxApiError(429, {"error": "too.many.requests"})
            return "ok"

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        result = await call_max_api_with_retry(
            "send_message",
            flaky_call,
            config=MaxApiRetryConfig(
                max_attempts=3,
                base_delay_sec=0.5,
                max_delay_sec=5.0,
                jitter_sec=0.0,
            ),
            observability=observability,
            idempotency="send",
            message_key_present=False,
            sleep=fake_sleep,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls, 2)
        self.assertEqual(sleeps, [0.5])
        actions = [record.action for record in repository.audit_records]
        self.assertIn("max_api_rate_limited", actions)
        self.assertIn("max_api_retry", actions)
        retry = next(record for record in repository.audit_records if record.action == "max_api_retry")
        self.assertEqual(retry.metadata["operation"], "send_message")
        self.assertEqual(retry.metadata["classification"], "rate_limited")
        self.assertEqual(retry.metadata["attempt"], 1)
        self.assertEqual(retry.metadata["max_attempts"], 3)

    async def test_retry_wrapper_stops_after_max_attempts(self) -> None:
        calls = 0
        repository = FakeObservabilityRepository()
        observability = ObservabilityService(repository=repository)

        async def always_limited():
            nonlocal calls
            calls += 1
            raise MaxApiError(429, {"error": "too.many.requests"})

        async def fake_sleep(delay: float) -> None:
            return None

        with self.assertRaises(MaxApiRetryExhausted):
            await call_max_api_with_retry(
                "edit_message",
                always_limited,
                config=MaxApiRetryConfig(max_attempts=2, jitter_sec=0.0),
                observability=observability,
                sleep=fake_sleep,
            )

        self.assertEqual(calls, 2)
        self.assertEqual(repository.audit_records[-1].action, "max_api_retry_exhausted")
        self.assertTrue(repository.audit_records[-1].metadata["retry_exhausted"])

    async def test_retry_wrapper_does_not_retry_permanent_error(self) -> None:
        calls = 0
        repository = FakeObservabilityRepository()
        observability = ObservabilityService(repository=repository)

        async def bad_request():
            nonlocal calls
            calls += 1
            raise MaxApiError(403, {"message": "forbidden"})

        with self.assertRaises(MaxApiError):
            await call_max_api_with_retry(
                "send_message",
                bad_request,
                observability=observability,
            )

        self.assertEqual(calls, 1)
        self.assertEqual(repository.audit_records[0].action, "max_api_permanent_error")
        self.assertEqual(repository.audit_records[0].metadata["classification"], "permanent")

    async def test_observability_write_failure_does_not_break_retry_success(self) -> None:
        calls = 0
        observability = ObservabilityService(repository=FakeObservabilityRepository(fail=True))

        async def flaky_call():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise MaxApiError(429, {"error": "too.many.requests"})
            return "ok"

        async def fake_sleep(delay: float) -> None:
            return None

        result = await call_max_api_with_retry(
            "edit_message",
            flaky_call,
            config=MaxApiRetryConfig(max_attempts=2, jitter_sec=0.0),
            observability=observability,
            sleep=fake_sleep,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls, 2)

    def test_redaction_masks_secrets_and_private_urls(self) -> None:
        raw = (
            "Bearer abc.def token=123 password=qwerty "
            "https://example.invalid/private/file?token=secret"
        )

        redacted = redact_sensitive(raw)

        self.assertNotIn("abc.def", redacted)
        self.assertNotIn("qwerty", redacted)
        self.assertNotIn("example.invalid", redacted)
        self.assertIn("[redacted]", redacted)

    async def test_observability_metadata_is_redacted(self) -> None:
        repository = FakeObservabilityRepository()
        observability = ObservabilityService(repository=repository)

        async def bad_request():
            raise MaxApiError(
                400,
                {
                    "message": (
                        "bad token=secret password=qwerty "
                        "https://example.invalid/private/file?token=secret"
                    )
                },
            )

        with self.assertRaises(MaxApiError):
            await call_max_api_with_retry(
                "send_message",
                bad_request,
                observability=observability,
            )

        serialized = json.dumps(repository.audit_records[0].metadata, ensure_ascii=False)
        self.assertNotIn("qwerty", serialized)
        self.assertNotIn("example.invalid", serialized)
        self.assertNotIn("token=secret", serialized)


if __name__ == "__main__":
    unittest.main()
