from pathlib import Path

from app.helpdesk.repositories.in_memory_ticket_repository import InMemoryTicketRepository
from app.helpdesk.repositories.sqlite_ticket_repository import SqliteTicketRepository
from app.helpdesk.services.ticket_link_service import TicketLinkService
from app.helpdesk.services.ticket_lifecycle_service import TicketLifecycleService
from app.helpdesk.services.user_flow_service import UserFlowService
from config.config import get_config


_ticket_service: TicketLifecycleService | None = None
_user_flow_service: UserFlowService | None = None
_ticket_link_service: TicketLinkService | None = None


def _build_ticket_service() -> TicketLifecycleService:
    cfg = get_config()

    if cfg.tickets.backend == "memory":
        repository = InMemoryTicketRepository()
    else:
        root_dir = Path(__file__).resolve().parents[2]
        db_path = Path(cfg.tickets.sqlite_path)
        if not db_path.is_absolute():
            db_path = root_dir / db_path
        repository = SqliteTicketRepository(str(db_path))

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


def get_ticket_link_service() -> TicketLinkService:
    global _ticket_link_service
    if _ticket_link_service is None:
        _ticket_link_service = TicketLinkService()
    return _ticket_link_service
