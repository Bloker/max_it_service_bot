import unittest

from maxapi.exceptions import MaxApiError

from app.bot.services.max_api_retry import (
    MaxApiRetryConfig,
    MaxApiRetryExhausted,
    call_max_api_with_retry,
    classify_max_api_error,
    redact_sensitive,
)


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
            sleep=fake_sleep,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls, 2)
        self.assertEqual(sleeps, [0.5])

    async def test_retry_wrapper_stops_after_max_attempts(self) -> None:
        calls = 0

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
                sleep=fake_sleep,
            )

        self.assertEqual(calls, 2)

    async def test_retry_wrapper_does_not_retry_permanent_error(self) -> None:
        calls = 0

        async def bad_request():
            nonlocal calls
            calls += 1
            raise MaxApiError(400, {"message": "bad payload"})

        with self.assertRaises(MaxApiError):
            await call_max_api_with_retry("send_message", bad_request)

        self.assertEqual(calls, 1)

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


if __name__ == "__main__":
    unittest.main()
