"""Фабрика singleton-сервиса observability."""

from app.observability.repositories.postgres_observability_repository import (
    PostgresObservabilityRepository,
)
from app.observability.services import ObservabilityService
from config.config import get_config

_observability_service: ObservabilityService | None = None


def get_observability_service() -> ObservabilityService:
    """Возвращает singleton audit/events service."""

    global _observability_service
    if _observability_service is not None:
        return _observability_service

    cfg = get_config()
    repository = None
    if cfg.tickets.backend == "postgres":
        repository = PostgresObservabilityRepository(
            host=cfg.tickets.postgres_host,
            port=cfg.tickets.postgres_port,
            database=cfg.tickets.postgres_db,
            user=cfg.tickets.postgres_user,
            password=cfg.tickets.postgres_password,
            sslmode=cfg.tickets.postgres_sslmode,
            connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
        )
    _observability_service = ObservabilityService(
        repository=repository,
        audit_enabled=cfg.observability.audit_enabled,
        ticket_events_enabled=cfg.observability.ticket_events_enabled,
        network_tool_runs_enabled=cfg.observability.network_tool_runs_enabled,
    )
    return _observability_service
