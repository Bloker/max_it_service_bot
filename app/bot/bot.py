"""Инициализация MAX Bot API, dispatcher, long polling и webhook."""

import asyncio
import logging
from time import monotonic
from typing import Any

from maxapi import Bot, Dispatcher

from app.bot.handlers import routes
from config.config import BotConfig
from config.config import get_config

logger = logging.getLogger(__name__)

VOICE_ATTACHMENT_TYPES = frozenset({
    "voice",
    "voice_message",
    "voice_note",
    "audiomessage",
    "audio_message",
    "audiomsg",
    "ptt",
})
VOICELESS_MESSAGE_UPDATE_FIELDS = frozenset({
    "timestamp",
    "user_locale",
    "update_type",
})


def _normalize_voice_attachments(events: dict[str, Any] | None) -> dict[str, Any] | None:
    """Приводит voice-вложения к типу ``audio`` до pydantic-валидации maxapi.

    MAX API может возвращать аудиосообщения с ``type`` вроде ``voice`` или
    ``audio_message``, которые не входят в discriminated union ``maxapi``.
    Без нормализации всё событие ``message_created`` отбрасывается на этапе
    парсинга, и handler никогда не вызывается.
    """

    if not events or not isinstance(events, dict):
        return events

    updates = events.get("updates")
    if not isinstance(updates, list):
        return events

    normalized_count = 0
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_type = update.get("update_type", "")
        if update_type != "message_created":
            continue

        _log_raw_update(update, update_type, reason="debug-all-message-created")

        message = update.get("message")
        if not isinstance(message, dict):
            update_fields = set(update.keys())
            if update_fields <= VOICELESS_MESSAGE_UPDATE_FIELDS:
                logger.warning(
                    "MessageCreated update without message payload cannot be handled: "
                    "fields=%s. MAX API did not provide message/mid for this update.",
                    sorted(update_fields),
                )
            continue
        body = message.get("body")
        if not isinstance(body, dict):
            continue
        attachments = body.get("attachments")
        if not isinstance(attachments, list):
            continue

        att_types = [
            att.get("type") if isinstance(att, dict) else type(att).__name__
            for att in attachments
        ]
        if att_types:
            logger.info(
                "Raw message_created attachments: types=%s",
                att_types,
            )

        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            att_type = attachment.get("type")
            if isinstance(att_type, str) and att_type.lower() in VOICE_ATTACHMENT_TYPES:
                logger.info(
                    "Normalizing voice attachment: original_type=%s -> audio",
                    att_type,
                )
                attachment["type"] = "audio"
                normalized_count += 1

    if normalized_count:
        logger.info(
            "Voice attachments normalized to audio: count=%s",
            normalized_count,
        )

    return events


def _log_raw_update(update: dict[str, Any], update_type: str, *, reason: str) -> None:
    """Логирует безопасные признаки update без raw payload и private URL."""

    message = update.get("message")
    body = message.get("body") if isinstance(message, dict) else None
    attachments = body.get("attachments") if isinstance(body, dict) else None
    attachment_types = []
    if isinstance(attachments, list):
        attachment_types = [
            attachment.get("type")
            for attachment in attachments
            if isinstance(attachment, dict)
        ]
    logger.warning(
        "Raw update debug: update_type=%s reason=%s fields=%s "
        "has_message=%s has_attachments=%s attachment_types=%s",
        update_type,
        reason,
        sorted(update.keys()),
        isinstance(message, dict),
        bool(attachments) if isinstance(attachments, list) else False,
        attachment_types,
    )


def register_routes(dp: Dispatcher) -> None:
    """Регистрирует все обработчики событий MAX в диспетчере."""

    for reg in routes:
        reg(dp)


def configure_long_polling_limits(bot: Bot, cfg: BotConfig) -> None:
    """Ограничивает long polling под текущие требования MAX API."""

    original_get_updates = bot.get_updates
    last_request_at = 0.0

    async def get_updates_with_limits(*, limit=None, timeout=None, marker=None, types=None):
        nonlocal last_request_at

        # MAX ограничивает частоту запросов; выдерживаем паузу между poll.
        elapsed = monotonic() - last_request_at
        if elapsed < cfg.polling_min_interval_sec:
            await asyncio.sleep(cfg.polling_min_interval_sec - elapsed)

        last_request_at = monotonic()
        events = await original_get_updates(
            limit=limit if limit is not None else cfg.polling_limit,
            timeout=timeout if timeout is not None else cfg.polling_timeout_sec,
            marker=marker,
            types=types,
        )
        return _normalize_voice_attachments(events)

    bot.get_updates = get_updates_with_limits


async def main() -> None:
    """Создает бота, регистрирует handlers и запускает выбранный режим."""

    cfg = get_config()

    bot = Bot(token=cfg.bot.token)
    dp = Dispatcher()

    from app.monitoring.tls.runtime import build_tls_reminder_service

    tls_reminder = build_tls_reminder_service(cfg=cfg, bot=bot)

    register_routes(dp)

    logger.info("Бот запускается: update_mode=%s", cfg.bot.update_mode)

    if tls_reminder is not None:
        tls_reminder.start()

    try:
        if cfg.bot.update_mode == "webhook":
            from app.bot.webhook_server import run_webhook_server

            logger.info(
                "Бот запущен в webhook-mode: host=%s port=%s path=%s health_path=%s",
                cfg.bot.webhook_host,
                cfg.bot.webhook_port,
                cfg.bot.webhook_path,
                cfg.bot.webhook_health_path,
            )
            await run_webhook_server(cfg=cfg.bot, dispatcher=dp, bot=bot)
            return

        configure_long_polling_limits(bot, cfg.bot)

        try:
            await bot.delete_webhook()
        except Exception as exc:
            logger.warning("Ошибка удаления webhook: %s", exc)

        logger.info(
            "Бот запущен и ожидает сообщений: polling_limit=%s polling_timeout=%s polling_min_interval=%s",
            cfg.bot.polling_limit,
            cfg.bot.polling_timeout_sec,
            cfg.bot.polling_min_interval_sec,
        )
        await dp.start_polling(bot, skip_updates=cfg.bot.skip_updates_on_start)
    finally:
        if tls_reminder is not None:
            await tls_reminder.stop()
