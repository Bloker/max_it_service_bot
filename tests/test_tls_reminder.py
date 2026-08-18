import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.monitoring.tls.models import TLSCertificateInfo, TLSReminderState
from app.monitoring.tls.service import TLSReminderService
from app.monitoring.tls.texts import render_tls_reminder

UTC = timezone.utc


class _Checker:
    def __init__(self, not_after: datetime):
        self.not_after = not_after
        self.calls = 0

    def check(self, *, host: str, port: int, timeout_sec: int):
        self.calls += 1
        return TLSCertificateInfo(host=host, port=port, not_after=self.not_after)


class _FailingChecker:
    def check(self, *, host: str, port: int, timeout_sec: int):
        raise TimeoutError()


class _Repository:
    def __init__(self):
        self.states = {}

    def get_state(self, host: str):
        return self.states.get(host)

    def save_state(self, host: str, state: TLSReminderState):
        self.states[host] = state


def _service(*, now, not_after, repository=None, sent=None):
    repository = repository or _Repository()
    sent = sent if sent is not None else []

    async def sender(text: str) -> bool:
        sent.append(text)
        return True

    async def run_sync(function, *args, **kwargs):
        return function(*args, **kwargs)

    return TLSReminderService(
        host="max.myservicedomain.ru",
        port=443,
        reminder_days=5,
        interval_sec=86400,
        timeout_sec=10,
        server_hint="192.168.1.177",
        checker=_Checker(not_after),
        repository=repository,
        sender=sender,
        now_provider=lambda: now,
        sync_runner=run_sync,
    ), repository, sent


class TLSReminderServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_runs_immediate_check_and_stop_cancels_task(self) -> None:
        now = datetime(2026, 9, 29, 8, tzinfo=UTC)
        service, _, sent = _service(now=now, not_after=now + timedelta(days=5))

        service.start()
        for _ in range(20):
            if sent:
                break
            await asyncio.sleep(0)
        await service.stop()

        self.assertEqual(len(sent), 1)

    async def test_six_days_remaining_does_not_send(self) -> None:
        now = datetime(2026, 9, 28, 8, tzinfo=UTC)
        service, _, sent = _service(now=now, not_after=now + timedelta(days=6))

        self.assertFalse(await service.check_once())
        self.assertEqual(sent, [])

    async def test_threshold_days_send_once(self) -> None:
        now = datetime(2026, 9, 29, 8, tzinfo=UTC)
        for days in (5, 4, 1):
            with self.subTest(days=days):
                service, _, sent = _service(
                    now=now,
                    not_after=now + timedelta(days=days),
                )
                self.assertTrue(await service.check_once())
                self.assertEqual(len(sent), 1)

    async def test_expired_certificate_sends_expired_message(self) -> None:
        now = datetime(2026, 10, 5, 8, tzinfo=UTC)
        service, _, sent = _service(now=now, not_after=now - timedelta(days=1))

        self.assertTrue(await service.check_once())
        self.assertIn("уже истёк", sent[0])

    async def test_same_certificate_is_not_sent_after_restart(self) -> None:
        now = datetime(2026, 9, 29, 8, tzinfo=UTC)
        not_after = now + timedelta(days=5)
        repository = _Repository()
        first, _, sent = _service(
            now=now,
            not_after=not_after,
            repository=repository,
        )
        second, _, _ = _service(
            now=now,
            not_after=not_after,
            repository=repository,
            sent=sent,
        )

        self.assertTrue(await first.check_once())
        self.assertFalse(await second.check_once())
        self.assertEqual(len(sent), 1)

    async def test_renewed_certificate_starts_new_cycle(self) -> None:
        now = datetime(2026, 9, 29, 8, tzinfo=UTC)
        repository = _Repository()
        repository.states["max.myservicedomain.ru"] = TLSReminderState(
            certificate_not_after=now + timedelta(days=1),
            reminder_sent_at=now - timedelta(days=1),
        )
        renewed_not_after = now + timedelta(days=90)
        service, _, sent = _service(
            now=now,
            not_after=renewed_not_after,
            repository=repository,
        )

        self.assertFalse(await service.check_once())
        self.assertEqual(sent, [])

        threshold_now = renewed_not_after - timedelta(days=5)
        threshold_service, _, _ = _service(
            now=threshold_now,
            not_after=renewed_not_after,
            repository=repository,
            sent=sent,
        )
        self.assertTrue(await threshold_service.check_once())
        self.assertEqual(len(sent), 1)

    async def test_network_error_does_not_escape(self) -> None:
        async def sender(text: str) -> bool:
            raise AssertionError("sender must not be called")

        async def run_sync(function, *args, **kwargs):
            return function(*args, **kwargs)

        service = TLSReminderService(
            host="max.myservicedomain.ru",
            port=443,
            reminder_days=5,
            interval_sec=86400,
            timeout_sec=10,
            server_hint="",
            checker=_FailingChecker(),
            repository=_Repository(),
            sender=sender,
            sync_runner=run_sync,
        )

        self.assertFalse(await service.check_once())


class TLSReminderTextTests(unittest.TestCase):
    def test_day_word_forms_and_zero(self) -> None:
        not_after = datetime(2026, 10, 4, 12, tzinfo=UTC)
        expected = {5: "5 дней", 2: "2 дня", 1: "1 день", 0: "0 дней"}
        for days, fragment in expected.items():
            with self.subTest(days=days):
                text = render_tls_reminder(
                    host="max.myservicedomain.ru",
                    not_after=not_after,
                    remaining_days=days,
                    server_hint="192.168.1.177",
                )
                self.assertIn(fragment, text)
                self.assertIn("04.10.2026", text)

    def test_expired_text(self) -> None:
        text = render_tls_reminder(
            host="max.myservicedomain.ru",
            not_after=datetime(2026, 10, 4, 12, tzinfo=UTC),
            remaining_days=-1,
            expired=True,
        )

        self.assertIn("уже истёк", text)


if __name__ == "__main__":
    unittest.main()
