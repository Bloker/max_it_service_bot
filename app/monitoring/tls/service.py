"""Фоновая логика проверки сертификата и отправки напоминания."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.monitoring.tls.certificate_checker import (
    TLSCertificateChecker,
    TLSCertificateCheckError,
)
from app.monitoring.tls.models import TLSReminderState
from app.monitoring.tls.repository import TLSReminderRepository
from app.monitoring.tls.texts import render_tls_reminder
from app.observability.services import ObservabilityService

logger = logging.getLogger(__name__)

ReminderSender = Callable[[str], Awaitable[bool]]
NowProvider = Callable[[], datetime]
SyncRunner = Callable[..., Awaitable]


class TLSReminderService:
    """Проверяет endpoint и один раз напоминает о каждом сертификате."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        reminder_days: int,
        interval_sec: int,
        timeout_sec: int,
        server_hint: str,
        checker: TLSCertificateChecker,
        repository: TLSReminderRepository,
        sender: ReminderSender,
        observability: ObservabilityService | None = None,
        now_provider: NowProvider | None = None,
        sync_runner: SyncRunner = asyncio.to_thread,
    ) -> None:
        self._host = host
        self._port = port
        self._reminder_days = reminder_days
        self._interval_sec = interval_sec
        self._timeout_sec = timeout_sec
        self._server_hint = server_hint
        self._checker = checker
        self._repository = repository
        self._sender = sender
        self._observability = observability
        self._now_provider = now_provider or (lambda: datetime.now(tz=timezone.utc))
        self._sync_runner = sync_runner
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Запускает единственную фоновую задачу с немедленной проверкой."""

        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(
            self.run_forever(),
            name="tls-certificate-reminder",
        )

    async def stop(self) -> None:
        """Корректно отменяет фоновую задачу при остановке бота."""

        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def run_forever(self) -> None:
        """Выполняет проверку сразу и затем с заданным интервалом."""

        while True:
            await self.check_once()
            await asyncio.sleep(self._interval_sec)

    async def check_once(self) -> bool:
        """Выполняет одну безопасную проверку; True означает отправку reminder."""

        try:
            certificate = await self._sync_runner(
                self._checker.check,
                host=self._host,
                port=self._port,
                timeout_sec=self._timeout_sec,
            )
            now = _as_utc(self._now_provider())
            not_after = _as_utc(certificate.not_after)
            expired = now > not_after
            remaining_days = (not_after.date() - now.date()).days
            await self._record_event(
                action="tls_certificate_checked",
                result="success",
                not_after=not_after,
                remaining_days=remaining_days,
            )
            logger.info(
                "TLS certificate check completed host=%s remaining_days=%s",
                self._host,
                remaining_days,
            )
            if not expired and remaining_days > self._reminder_days:
                return False

            state = await self._sync_runner(self._repository.get_state, self._host)
            if state is not None and state.certificate_not_after == not_after:
                return False

            text = render_tls_reminder(
                host=self._host,
                not_after=not_after,
                remaining_days=remaining_days,
                server_hint=self._server_hint,
                expired=expired,
            )
            if not await self._sender(text):
                await self._record_event(
                    action="tls_certificate_reminder_sent",
                    result="failed",
                    not_after=not_after,
                    remaining_days=remaining_days,
                )
                return False

            sent_at = _as_utc(self._now_provider())
            await self._sync_runner(
                self._repository.save_state,
                self._host,
                TLSReminderState(
                    certificate_not_after=not_after,
                    reminder_sent_at=sent_at,
                ),
            )
            await self._record_event(
                action="tls_certificate_reminder_sent",
                result="success",
                not_after=not_after,
                remaining_days=remaining_days,
            )
            logger.info(
                "TLS certificate reminder sent host=%s not_after=%s",
                self._host,
                not_after.isoformat(),
            )
            return True
        except TLSCertificateCheckError as exc:
            await self._handle_failure(exc)
            return False
        except Exception as exc:
            await self._handle_failure(exc)
            return False

    async def _handle_failure(self, exc: Exception) -> None:
        logger.warning(
            "TLS certificate check failed host=%s error_class=%s",
            self._host,
            exc.__class__.__name__,
        )
        await self._record_event(
            action="tls_certificate_check_failed",
            result="failed",
        )

    async def _record_event(
        self,
        *,
        action: str,
        result: str,
        not_after: datetime | None = None,
        remaining_days: int | None = None,
    ) -> None:
        if self._observability is None:
            return
        metadata: dict[str, str | int] = {
            "host": self._host,
            "port": self._port,
            "result": result,
        }
        if not_after is not None:
            metadata["not_after"] = not_after.isoformat()
        if remaining_days is not None:
            metadata["remaining_days"] = remaining_days
        await self._observability.audit(
            action=action,
            resource_type="tls_certificate",
            resource_id=self._host,
            result=result,
            metadata=metadata,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)
