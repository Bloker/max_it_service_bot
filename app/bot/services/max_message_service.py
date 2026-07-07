"""Безопасные операции с сообщениями MAX."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from maxapi.enums.message_link_type import MessageLinkType
from maxapi.enums.parse_mode import ParseMode
from maxapi.types.message import NewMessageLink

from app.bot.services.max_api_retry import (
    MaxApiRetryConfig,
    MaxApiRetryExhausted,
    call_max_api_with_retry,
    classify_max_api_error,
)
from app.observability.services import ObservabilityService

logger = logging.getLogger(__name__)

_MAX_EDIT_LIMITER_SIZE = 512


class MaxMessageService:
    """Инкапсулирует update/send/answer операции MAX API."""

    def __init__(
        self,
        observability: ObservabilityService | None = None,
        retry_config: MaxApiRetryConfig | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._observability = observability
        self._retry_config = retry_config or MaxApiRetryConfig()
        self._sleep = sleep
        self._monotonic = monotonic
        self._edit_locks: dict[str, asyncio.Lock] = {}
        self._edit_last_at: dict[str, float] = {}

    async def edit_message(
        self,
        *,
        bot,
        message_id: str,
        text: str,
        attachments: list[Any] | None = None,
        text_format: ParseMode | None = ParseMode.HTML,
        notify: bool = False,
    ) -> bool:
        """Редактирует сообщение бота."""

        lock = self._get_edit_lock(str(message_id))
        async with lock:
            await self._wait_for_edit_slot(str(message_id))
            return await self._edit_message_unlocked(
                bot=bot,
                message_id=str(message_id),
                text=text,
                attachments=attachments,
                text_format=text_format,
                notify=notify,
            )

    async def _edit_message_unlocked(
        self,
        *,
        bot,
        message_id: str,
        text: str,
        attachments: list[Any] | None,
        text_format: ParseMode | None,
        notify: bool,
    ) -> bool:
        try:
            await call_max_api_with_retry(
                "edit_message",
                lambda: bot.edit_message(
                    message_id=str(message_id),
                    text=text,
                    attachments=attachments,
                    notify=notify,
                    format=text_format,
                ),
                config=self._retry_config,
                retry_network_errors=True,
                sleep=self._sleep,
            )
        except Exception as exc:
            self._log_max_failure("MAX edit_message failed: message_id=%s", exc, message_id)
            await self._audit_max_message(
                action="max_message_edit_failed",
                resource_id=str(message_id),
                result="failed",
            )
            return False
        self._edit_last_at[str(message_id)] = self._monotonic()
        self._trim_edit_limiter()
        await self._audit_max_message(
            action="max_message_edit_success",
            resource_id=str(message_id),
            result="success",
        )
        return True

    async def send_message(
        self,
        *,
        bot,
        chat_id: int | None = None,
        user_id: int | None = None,
        text: str,
        attachments: list[Any] | None = None,
        reply_to_message_id: str | None = None,
        text_format: ParseMode | None = ParseMode.HTML,
        notify: bool = False,
    ) -> str | None:
        """Отправляет сообщение в чат или личный диалог пользователя."""

        link = None
        if reply_to_message_id:
            link = NewMessageLink(
                type=MessageLinkType.REPLY,
                mid=str(reply_to_message_id),
            )

        try:
            if chat_id is not None:
                sent = await call_max_api_with_retry(
                    "send_message",
                    lambda: bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        attachments=attachments,
                        link=link,
                        notify=notify,
                        format=text_format,
                    ),
                    config=self._retry_config,
                    retry_network_errors=False,
                    sleep=self._sleep,
                )
            else:
                sent = await call_max_api_with_retry(
                    "send_message",
                    lambda: bot.send_message(
                        user_id=user_id,
                        text=text,
                        attachments=attachments,
                        link=link,
                        notify=notify,
                        format=text_format,
                    ),
                    config=self._retry_config,
                    retry_network_errors=False,
                    sleep=self._sleep,
                )
        except Exception as exc:
            self._log_max_failure(
                "MAX send_message failed: chat_id=%s user_id=%s",
                exc,
                chat_id,
                user_id,
            )
            await self._audit_max_message(
                action="max_message_send_failed",
                resource_id=str(chat_id or user_id or "unknown"),
                result="failed",
                metadata={"target_type": "chat" if chat_id is not None else "user"},
            )
            return None

        message = getattr(sent, "message", None)
        body = getattr(message, "body", None)
        mid = getattr(body, "mid", None)
        message_id = str(mid) if mid else None
        await self._audit_max_message(
            action="max_message_sent",
            resource_id=message_id or str(chat_id or user_id or "unknown"),
            result="success" if message_id else "failed",
            metadata={"target_type": "chat" if chat_id is not None else "user"},
        )
        return message_id

    async def delete_message(self, *, bot, message_id: str | None) -> bool:
        """Удаляет сообщение, если известен его идентификатор."""

        if not message_id:
            return False
        try:
            await call_max_api_with_retry(
                "delete_message",
                lambda: bot.delete_message(message_id=str(message_id)),
                config=self._retry_config,
                retry_network_errors=True,
                sleep=self._sleep,
            )
        except Exception as exc:
            self._log_max_failure("MAX delete_message failed: message_id=%s", exc, message_id)
            await self._audit_max_message(
                action="max_message_delete_failed",
                resource_id=str(message_id),
                result="failed",
            )
            return False
        await self._audit_max_message(
            action="max_message_delete_success",
            resource_id=str(message_id),
            result="success",
        )
        return True

    async def answer_callback(self, *, event, notification: str) -> bool:
        """Отвечает на callback."""

        try:
            await call_max_api_with_retry(
                "callback_answer",
                lambda: event.answer(notification=notification),
                config=self._retry_config,
                retry_network_errors=True,
                sleep=self._sleep,
            )
        except Exception as exc:
            self._log_max_failure(
                "MAX callback answer failed: notification=%s",
                exc,
                notification,
            )
            await self._audit_max_message(
                action="max_callback_answer_failed",
                resource_id="callback",
                result="failed",
            )
            return False
        await self._audit_max_message(
            action="max_callback_answer_success",
            resource_id="callback",
            result="success",
        )
        return True

    async def answer_callback_with_message(
        self,
        *,
        event,
        text: str,
        attachments: list[Any] | None = None,
        notification: str | None = None,
        text_format: ParseMode | None = ParseMode.HTML,
        notify: bool = False,
    ) -> bool:
        """Отвечает на callback с заменой текста и кнопок сообщения."""

        message_id = _extract_event_message_id(event)
        if message_id:
            lock = self._get_edit_lock(message_id)
            async with lock:
                await self._wait_for_edit_slot(message_id)
                return await self._answer_callback_with_message_unlocked(
                    event=event,
                    text=text,
                    attachments=attachments,
                    notification=notification,
                    text_format=text_format,
                    notify=notify,
                    message_id=message_id,
                )
        return await self._answer_callback_with_message_unlocked(
            event=event,
            text=text,
            attachments=attachments,
            notification=notification,
            text_format=text_format,
            notify=notify,
            message_id=None,
        )

    async def _answer_callback_with_message_unlocked(
        self,
        *,
        event,
        text: str,
        attachments: list[Any] | None,
        notification: str | None,
        text_format: ParseMode | None,
        notify: bool,
        message_id: str | None,
    ) -> bool:
        """Выполняет callback answer update после локального rate limit."""

        try:
            await call_max_api_with_retry(
                "callback_answer_with_message",
                lambda: event.answer(
                    new_text=text,
                    attachments=attachments or [],
                    notification=notification,
                    notify=notify,
                    format=text_format,
                ),
                config=self._retry_config,
                retry_network_errors=True,
                sleep=self._sleep,
            )
        except Exception as exc:
            self._log_max_failure("MAX callback message update failed", exc)
            await self._audit_max_message(
                action="max_callback_answer_failed",
                resource_id="callback",
                result="failed",
                metadata={"with_message_update": True},
            )
            return False
        if message_id:
            self._edit_last_at[message_id] = self._monotonic()
            self._trim_edit_limiter()
        await self._audit_max_message(
            action="max_callback_answer_success",
            resource_id="callback",
            result="success",
            metadata={"with_message_update": True},
        )
        return True

    async def _audit_max_message(
        self,
        *,
        action: str,
        resource_id: str,
        result: str,
        metadata: dict | None = None,
    ) -> None:
        """Пишет audit MAX API операции без текста сообщений и вложений."""

        if self._observability is None:
            return
        await self._observability.audit(
            action=action,
            resource_type="max_message",
            resource_id=resource_id,
            result=result,
            metadata=metadata or {},
        )

    async def _wait_for_edit_slot(self, message_id: str) -> None:
        """Ограничивает частоту edit конкретного сообщения."""

        min_interval = self._retry_config.edit_min_interval_sec
        if min_interval <= 0:
            return
        last_at = self._edit_last_at.get(message_id)
        if last_at is None:
            return
        wait_for = min_interval - (self._monotonic() - last_at)
        if wait_for > 0:
            logger.info(
                "MAX edit_message rate limited locally: message_id=%s delay=%.3f",
                message_id,
                wait_for,
            )
            await self._sleep(wait_for)

    def _get_edit_lock(self, message_id: str) -> asyncio.Lock:
        lock = self._edit_locks.get(message_id)
        if lock is None:
            lock = asyncio.Lock()
            self._edit_locks[message_id] = lock
        return lock

    def _trim_edit_limiter(self) -> None:
        """Ограничивает рост in-memory карты edit limiter."""

        if len(self._edit_last_at) <= _MAX_EDIT_LIMITER_SIZE:
            return
        removable = sorted(self._edit_last_at.items(), key=lambda item: item[1])
        for message_id, _ in removable[: max(1, len(removable) - _MAX_EDIT_LIMITER_SIZE)]:
            lock = self._edit_locks.get(message_id)
            if lock is not None and lock.locked():
                continue
            self._edit_last_at.pop(message_id, None)
            self._edit_locks.pop(message_id, None)

    def _log_max_failure(self, message: str, exc: Exception, *args) -> None:
        if isinstance(exc, MaxApiRetryExhausted):
            info = exc.info
        else:
            info = classify_max_api_error(exc)
        if (
            isinstance(exc, MaxApiRetryExhausted)
            or info.transient
            or (info.status_code is not None and 400 <= info.status_code < 500)
        ):
            logger.warning(
                "%s status=%s code=%s",
                message % args if args else message,
                info.status_code,
                info.code,
            )
            return
        logger.exception(message, *args)


def _extract_event_message_id(event) -> str | None:
    body = getattr(getattr(event, "message", None), "body", None)
    mid = getattr(body, "mid", None)
    return str(mid) if mid else None
