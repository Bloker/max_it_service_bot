"""Aiohttp-сервер для webhook-режима MAX Bot API."""

import asyncio
import hmac
import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from time import monotonic
from typing import Any

from aiohttp import web
from maxapi import Bot, Dispatcher
from maxapi.methods.types.getted_updates import process_update_webhook

from app.bot.bot import _normalize_voice_attachments
from config.config import BotConfig

logger = logging.getLogger(__name__)

UpdateProcessor = Callable[[dict[str, Any]], Awaitable[bool]]
WEBHOOK_SECRET_KEY = web.AppKey("webhook_secret", str)
UPDATE_PROCESSOR_KEY = web.AppKey("update_processor", UpdateProcessor)
WEBHOOK_ADAPTER_KEY = web.AppKey("webhook_adapter", Any)


def _build_safe_update_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Возвращает безопасные признаки update без raw payload и private URL."""

    message = payload.get("message")
    body = message.get("body") if isinstance(message, dict) else None
    attachments = body.get("attachments") if isinstance(body, dict) else None
    callback = payload.get("callback")
    user = callback.get("user") if isinstance(callback, dict) else None

    return {
        "update_type": payload.get("update_type"),
        "has_message": isinstance(message, dict),
        "has_mid": bool(message.get("mid")) if isinstance(message, dict) else False,
        "has_callback": isinstance(callback, dict),
        "has_attachments": bool(attachments) if isinstance(attachments, list) else False,
        "attachments_count": len(attachments) if isinstance(attachments, list) else 0,
        "chat_id": message.get("chat_id") if isinstance(message, dict) else payload.get("chat_id"),
        "user_id": user.get("user_id") if isinstance(user, dict) else None,
    }


class MaxWebhookUpdateAdapter:
    """Преобразует JSON webhook update в модель maxapi и вызывает Dispatcher."""

    def __init__(self, *, dispatcher: Dispatcher, bot: Bot) -> None:
        self._dispatcher = dispatcher
        self._bot = bot

    async def startup(self) -> None:
        """Готовит Dispatcher так же, как это делает maxapi webhook."""

        await self._dispatcher.startup(self._bot)

    async def process(self, payload: dict[str, Any]) -> bool:
        """Передает одно webhook-событие в существующую цепочку handlers."""

        normalized_payload = _normalize_voice_attachments({"updates": [payload]})
        update_payload = normalized_payload["updates"][0]
        event_object = await process_update_webhook(
            event_json=update_payload,
            bot=self._bot,
        )
        if event_object is None:
            logger.warning(
                "Webhook update ignored: update_type=%s",
                payload.get("update_type"),
            )
            return False

        await self._dispatcher.handle(event_object)
        return True


async def _default_startup(app: web.Application) -> None:
    """Инициализирует adapter при старте aiohttp-приложения."""

    adapter = app[WEBHOOK_ADAPTER_KEY]
    await adapter.startup()


async def handle_health(request: web.Request) -> web.Response:
    """Возвращает безопасный health-check без секретов и данных заявок."""

    return web.json_response(
        {
            "status": "ok",
            "service": "max-it-bot",
            "mode": "webhook",
        }
    )


async def handle_webhook(request: web.Request) -> web.Response:
    """Проверяет secret, JSON и передает update в Dispatcher."""

    secret = request.app[WEBHOOK_SECRET_KEY]
    if secret:
        incoming = request.headers.get("X-Max-Bot-Api-Secret", "")
        if not hmac.compare_digest(incoming, secret):
            logger.warning("Webhook rejected: invalid secret header")
            return web.json_response(
                {"ok": False, "error": "forbidden"},
                status=HTTPStatus.FORBIDDEN,
            )

    started_at = monotonic()
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Webhook rejected: invalid json")
        return web.json_response(
            {"ok": False, "error": "invalid_json"},
            status=HTTPStatus.BAD_REQUEST,
        )

    if not isinstance(payload, dict) or not payload:
        logger.warning("Webhook rejected: empty or non-object payload")
        return web.json_response(
            {"ok": False, "error": "invalid_payload"},
            status=HTTPStatus.BAD_REQUEST,
        )

    summary = _build_safe_update_summary(payload)
    try:
        accepted = await request.app[UPDATE_PROCESSOR_KEY](payload)
    except Exception:
        logger.exception(
            "Webhook update processing failed: summary=%s",
            summary,
        )
        return web.json_response(
            {"ok": False, "error": "processing_failed"},
            status=HTTPStatus.OK,
        )

    elapsed_ms = int((monotonic() - started_at) * 1000)
    logger.info(
        "Webhook update processed: accepted=%s elapsed_ms=%s summary=%s",
        accepted,
        elapsed_ms,
        summary,
    )
    return web.json_response({"ok": True}, status=HTTPStatus.OK)


def create_webhook_app(
    *,
    cfg: BotConfig,
    update_processor: UpdateProcessor,
    startup_handler: Callable[[web.Application], Awaitable[None]] | None = _default_startup,
) -> web.Application:
    """Создает aiohttp-приложение webhook-mode с health и MAX endpoint."""

    app = web.Application()
    app[WEBHOOK_SECRET_KEY] = cfg.webhook_secret
    app[UPDATE_PROCESSOR_KEY] = update_processor

    if startup_handler is not None:
        app.on_startup.append(startup_handler)

    app.router.add_get(cfg.webhook_health_path, handle_health)
    app.router.add_post(cfg.webhook_path, handle_webhook)
    return app


async def run_webhook_server(*, cfg: BotConfig, dispatcher: Dispatcher, bot: Bot) -> None:
    """Запускает внутренний aiohttp-сервер webhook-mode."""

    adapter = MaxWebhookUpdateAdapter(dispatcher=dispatcher, bot=bot)
    app = create_webhook_app(cfg=cfg, update_processor=adapter.process)
    app[WEBHOOK_ADAPTER_KEY] = adapter

    if not cfg.webhook_secret:
        logger.warning("Webhook secret is not configured; endpoint accepts unsigned requests")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=cfg.webhook_host, port=cfg.webhook_port)
    await site.start()

    logger.info(
        "Webhook server started: host=%s port=%s path=%s health_path=%s",
        cfg.webhook_host,
        cfg.webhook_port,
        cfg.webhook_path,
        cfg.webhook_health_path,
    )

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
