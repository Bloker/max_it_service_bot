from pathlib import Path

from app.helpdesk.repositories.in_memory_ticket_repository import InMemoryTicketRepository
from app.helpdesk.repositories.sqlite_ticket_repository import SqliteTicketRepository
from app.helpdesk.services.postgres_ticket_link_service import PostgresTicketLinkService
from app.helpdesk.services.ticket_link_service import TicketLinkService
from app.helpdesk.services.ticket_lifecycle_service import TicketLifecycleService
from app.helpdesk.services.user_flow_service import UserFlowService
from config.config import get_config


_ticket_service: TicketLifecycleService | None = None
_user_flow_service: UserFlowService | None = None
_ticket_link_service: TicketLinkService | PostgresTicketLinkService | None = None


def _build_ticket_service() -> TicketLifecycleService:
    cfg = get_config()

    if cfg.tickets.backend == "memory":
        repository = InMemoryTicketRepository()
    elif cfg.tickets.backend == "sqlite":
        root_dir = Path(__file__).resolve().parents[2]
        db_path = Path(cfg.tickets.sqlite_path)
        if not db_path.is_absolute():
            db_path = root_dir / db_path
        repository = SqliteTicketRepository(str(db_path))
    elif cfg.tickets.backend == "postgres":
        from app.helpdesk.repositories.postgres_ticket_repository import PostgresTicketRepository

        repository = PostgresTicketRepository(
            host=cfg.tickets.postgres_host,
            port=cfg.tickets.postgres_port,
            database=cfg.tickets.postgres_db,
            user=cfg.tickets.postgres_user,
            password=cfg.tickets.postgres_password,
            sslmode=cfg.tickets.postgres_sslmode,
            connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
        )
    else:
        raise RuntimeError(f"Unsupported ticket backend: {cfg.tickets.backend}")

    return TicketLifecycleService(repository=repository)


def get_ticket_service() -> TicketLifecycleService:
    global _ticket_service
    if _ticket_service is None:
        _ticket_service = _build_ticket_service()
    return _ticket_service


def get_user_flow_service() -> UserFlowService:
    global _user_flow_service
    if _user_flow_service is None:
        _user_flow_service = UserFlowService()
    return _user_flow_service


def get_ticket_link_service() -> TicketLinkService | PostgresTicketLinkService:
    global _ticket_link_service
    if _ticket_link_service is None:
        cfg = get_config()
        if cfg.tickets.backend == "postgres":
            _ticket_link_service = PostgresTicketLinkService(
                host=cfg.tickets.postgres_host,
                port=cfg.tickets.postgres_port,
                database=cfg.tickets.postgres_db,
                user=cfg.tickets.postgres_user,
                password=cfg.tickets.postgres_password,
                sslmode=cfg.tickets.postgres_sslmode,
                connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
            )
        else:
            _ticket_link_service = TicketLinkService()
    return _ticket_link_service
