"""Retry/backoff для временных ошибок MAX API."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)
_QUERY_SECRET_RE = re.compile(
    r"(token|secret|password|api[_-]?key)=([^&\s]+)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


@dataclass(frozen=True)
class MaxApiRetryConfig:
    """Настройки retry/backoff MAX API."""

    max_attempts: int = 4
    base_delay_sec: float = 0.5
    max_delay_sec: float = 5.0
    jitter_sec: float = 0.25
    server_error_attempts: int = 2
    edit_min_interval_sec: float = 1.0


@dataclass(frozen=True)
class MaxApiErrorInfo:
    """Классификация ошибки MAX API без секретов и raw payload."""

    status_code: int | None = None
    code: str | None = None
    message: str | None = None
    retry_after_sec: float | None = None
    rate_limited: bool = False
    server_error: bool = False
    network_error: bool = False

    @property
    def transient(self) -> bool:
        """Возвращает True для ошибок, которые можно ограниченно повторить."""

        return self.rate_limited or self.server_error or self.network_error


class MaxApiRetryExhausted(Exception):
    """MAX API временно недоступен после всех retry."""

    def __init__(self, operation_name: str, attempts: int, info: MaxApiErrorInfo) -> None:
        self.operation_name = operation_name
        self.attempts = attempts
        self.info = info
        super().__init__(operation_name, attempts, info.status_code, info.code)


def redact_sensitive(value: Any) -> str:
    """Маскирует секреты, токены и приватные URL перед записью в лог."""

    text = str(value)
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    text = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    text = _URL_RE.sub("[redacted-url]", text)
    return text


def classify_max_api_error(exc: BaseException) -> MaxApiErrorInfo:
    """Классифицирует ошибку maxapi/aiohttp без зависимости от конкретного класса."""

    raw = getattr(exc, "raw", None)
    status_code = _extract_status_code(exc, raw)
    code = _extract_error_code(exc, raw)
    message = _extract_message(exc, raw)
    retry_after = _extract_retry_after(exc, raw)
    haystack = " ".join(
        part.lower()
        for part in (str(status_code or ""), code or "", message or "")
        if part
    )
    rate_limited = status_code == 429 or "too.many.requests" in haystack
    server_error = (
        status_code in {500, 502, 503, 504}
        or "internal.error" in haystack
        or "server error" in haystack
    )
    network_error = _is_network_error(exc)
    return MaxApiErrorInfo(
        status_code=status_code,
        code=redact_sensitive(code) if code else None,
        message=redact_sensitive(message) if message else None,
        retry_after_sec=retry_after,
        rate_limited=rate_limited,
        server_error=server_error,
        network_error=network_error,
    )


async def call_max_api_with_retry(
    operation_name: str,
    call: Callable[[], Awaitable[T]],
    *,
    config: MaxApiRetryConfig | None = None,
    retry_network_errors: bool = False,
    max_attempts: int | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Выполняет MAX API вызов с ограниченным retry для 429/5xx."""

    settings = config or MaxApiRetryConfig()
    attempts_limit = max_attempts or settings.max_attempts
    attempt = 1
    while True:
        try:
            return await call()
        except Exception as exc:
            info = classify_max_api_error(exc)
            retryable = info.transient and (retry_network_errors or not info.network_error)
            if info.server_error and not info.rate_limited:
                attempts_limit = min(attempts_limit, settings.server_error_attempts)
            if not retryable:
                raise
            if attempt >= attempts_limit:
                logger.warning(
                    "max_api_retry_exhausted operation=%s status=%s code=%s attempts=%s",
                    operation_name,
                    info.status_code,
                    info.code,
                    attempt,
                )
                raise MaxApiRetryExhausted(operation_name, attempt, info) from exc
            delay = _calculate_delay(settings, attempt, info, jitter)
            logger.warning(
                "max_api_transient_error operation=%s status=%s code=%s attempt=%s next_delay=%.3f",
                operation_name,
                info.status_code,
                info.code,
                attempt,
                delay,
            )
            await sleep(delay)
            attempt += 1


def _calculate_delay(
    settings: MaxApiRetryConfig,
    attempt: int,
    info: MaxApiErrorInfo,
    jitter: Callable[[], float],
) -> float:
    if info.retry_after_sec is not None:
        return max(0.0, min(info.retry_after_sec, settings.max_delay_sec))
    base = max(0.0, settings.base_delay_sec)
    delay = base * (2 ** max(0, attempt - 1))
    if settings.jitter_sec > 0:
        delay += jitter() * settings.jitter_sec
    return min(delay, settings.max_delay_sec)


def _extract_status_code(exc: BaseException, raw: Any) -> int | None:
    for attr in ("status", "status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    for attr in ("status", "status_code"):
        value = getattr(response, attr, None)
        if isinstance(value, int):
            return value
    if isinstance(raw, dict):
        for key in ("status", "status_code", "code"):
            value = raw.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def _extract_error_code(exc: BaseException, raw: Any) -> str | None:
    for attr in ("error_code", "error", "name"):
        value = getattr(exc, attr, None)
        if value:
            return str(value)
    if isinstance(raw, dict):
        for key in ("error", "error_code", "name", "code"):
            value = raw.get(key)
            if value and not isinstance(value, int):
                return str(value)
    return None


def _extract_message(exc: BaseException, raw: Any) -> str | None:
    value = getattr(exc, "message", None)
    if value:
        return str(value)
    if isinstance(raw, dict):
        for key in ("message", "description", "error_description"):
            value = raw.get(key)
            if value:
                return str(value)
    if exc.args:
        return " ".join(str(arg) for arg in exc.args if not isinstance(arg, dict))
    return None


def _extract_retry_after(exc: BaseException, raw: Any) -> float | None:
    for attr in ("retry_after", "retry_after_sec"):
        value = getattr(exc, attr, None)
        parsed = _parse_retry_after(value)
        if parsed is not None:
            return parsed
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        parsed = _parse_retry_after(headers.get("Retry-After"))
        if parsed is not None:
            return parsed
    if isinstance(raw, dict):
        for key in ("retry_after", "retryAfter", "Retry-After"):
            parsed = _parse_retry_after(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_retry_after(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True
    module = exc.__class__.__module__
    name = exc.__class__.__name__.lower()
    return (
        module.startswith("aiohttp")
        and any(marker in name for marker in ("timeout", "connector", "clientconnection"))
    )
