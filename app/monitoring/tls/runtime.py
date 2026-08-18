"""Сборка TLS reminder из runtime-конфигурации приложения."""

import logging

from app.bot.services.max_message_service import MaxMessageService
from app.monitoring.tls.certificate_checker import TLSCertificateChecker
from app.monitoring.tls.postgres_repository import PostgresTLSReminderRepository
from app.monitoring.tls.service import TLSReminderService
from app.observability.runtime import get_observability_service
from config.config import AppConfig

logger = logging.getLogger(__name__)


def build_tls_reminder_service(*, cfg: AppConfig, bot) -> TLSReminderService | None:
    """Создаёт reminder только для включённого PostgreSQL runtime."""

    if not cfg.tls_reminder.enabled:
        return None
    if cfg.tickets.backend != "postgres":
        logger.warning(
            "TLS reminder disabled: persistent PostgreSQL backend is required"
        )
        return None

    observability = get_observability_service()
    messages = MaxMessageService(
        observability=observability,
        retry_config=cfg.max_api,
    )
    repository = PostgresTLSReminderRepository(
        host=cfg.tickets.postgres_host,
        port=cfg.tickets.postgres_port,
        database=cfg.tickets.postgres_db,
        user=cfg.tickets.postgres_user,
        password=cfg.tickets.postgres_password,
        sslmode=cfg.tickets.postgres_sslmode,
        connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
    )

    async def send_reminder(text: str) -> bool:
        message_id = await messages.send_message(
            bot=bot,
            chat_id=cfg.bot.group_chat_id,
            text=text,
            text_format=None,
            notify=True,
        )
        return message_id is not None

    return TLSReminderService(
        host=cfg.tls_reminder.host,
        port=cfg.tls_reminder.port,
        reminder_days=cfg.tls_reminder.reminder_days,
        interval_sec=cfg.tls_reminder.interval_sec,
        timeout_sec=cfg.tls_reminder.timeout_sec,
        server_hint=cfg.tls_reminder.server_hint,
        checker=TLSCertificateChecker(),
        repository=repository,
        sender=send_reminder,
        observability=observability,
    )
