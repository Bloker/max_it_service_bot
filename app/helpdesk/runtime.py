"""Фабрики singleton-сервисов HelpDesk."""

from pathlib import Path

from app.helpdesk.repositories.in_memory_ticket_repository import InMemoryTicketRepository
from app.helpdesk.repositories.sqlite_ticket_repository import SqliteTicketRepository
from app.helpdesk.services.postgres_ticket_link_service import PostgresTicketLinkService
from app.helpdesk.services.clarification_session_service import ClarificationSessionService
from app.helpdesk.services.close_reply_session_service import CloseReplySessionService
from app.helpdesk.services.knowledge_article_create_session_service import (
    KnowledgeArticleCreateSessionService,
)
from app.helpdesk.services.knowledge_base_service import KnowledgeBaseService
from app.helpdesk.services.media_attachment_service import MediaAttachmentService
from app.helpdesk.services.media_collection_session_service import MediaCollectionSessionService
from app.helpdesk.services.ticket_internal_comment_session_service import (
    TicketInternalCommentSessionService,
)
from app.helpdesk.services.ticket_internal_comment_service import TicketInternalCommentService
from app.helpdesk.services.ticket_clarification_service import TicketClarificationService
from app.helpdesk.services.room_history_service import RoomHistoryService
from app.helpdesk.services.ticket_link_service import TicketLinkService
from app.helpdesk.services.ticket_lifecycle_service import TicketLifecycleService
from app.helpdesk.services.user_reply_session_service import UserReplySessionService
from app.helpdesk.services.user_addition_session_service import UserAdditionSessionService
from app.helpdesk.services.ticket_user_addition_service import TicketUserAdditionService
from app.helpdesk.services.user_flow_service import UserFlowService
from app.observability.runtime import get_observability_service
from config.config import get_config


_ticket_service: TicketLifecycleService | None = None
_user_flow_service: UserFlowService | None = None
_ticket_link_service: TicketLinkService | PostgresTicketLinkService | None = None
_clarification_session_service: ClarificationSessionService | None = None
_close_reply_session_service: CloseReplySessionService | None = None
_ticket_internal_comment_session_service: TicketInternalCommentSessionService | None = None
_ticket_internal_comment_service: TicketInternalCommentService | None = None
_knowledge_article_create_session_service: KnowledgeArticleCreateSessionService | None = None
_knowledge_base_service: KnowledgeBaseService | None = None
_media_attachment_service: MediaAttachmentService | None = None
_media_collection_session_service: MediaCollectionSessionService | None = None
_ticket_clarification_service: TicketClarificationService | None = None
_user_reply_session_service: UserReplySessionService | None = None
_user_addition_session_service: UserAdditionSessionService | None = None
_ticket_user_addition_service: TicketUserAdditionService | None = None
_room_ticket_context_service = None
_room_history_service: RoomHistoryService | None = None


def _build_ticket_service() -> TicketLifecycleService:
    """Собирает сервис заявок с репозиторием из конфигурации."""

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

        legacy_repository = PostgresTicketRepository(
            host=cfg.tickets.postgres_host,
            port=cfg.tickets.postgres_port,
            database=cfg.tickets.postgres_db,
            user=cfg.tickets.postgres_user,
            password=cfg.tickets.postgres_password,
            sslmode=cfg.tickets.postgres_sslmode,
            connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
        )
        if cfg.tickets.schema_mode == "legacy":
            repository = legacy_repository
        elif cfg.tickets.schema_mode == "normalized":
            from app.helpdesk.repositories.postgres_normalized_ticket_repository import (
                PostgresNormalizedTicketRepository,
            )

            repository = PostgresNormalizedTicketRepository(cfg.tickets)
        elif cfg.tickets.schema_mode == "shadow_read":
            from app.helpdesk.repositories.postgres_normalized_ticket_repository import (
                PostgresNormalizedTicketRepository,
            )
            from app.helpdesk.repositories.shadow_ticket_repository import (
                ShadowReadTicketRepository,
            )

            repository = ShadowReadTicketRepository(
                primary=legacy_repository,
                shadow=PostgresNormalizedTicketRepository(cfg.tickets),
            )
        else:
            raise RuntimeError(f"Unsupported ticket schema mode: {cfg.tickets.schema_mode}")
    else:
        raise RuntimeError(f"Unsupported ticket backend: {cfg.tickets.backend}")

    return TicketLifecycleService(
        repository=repository,
        observability=get_observability_service(),
    )


def get_ticket_service() -> TicketLifecycleService:
    """Возвращает singleton сервиса жизненного цикла заявок."""

    global _ticket_service
    if _ticket_service is None:
        _ticket_service = _build_ticket_service()
    return _ticket_service


def get_user_flow_service() -> UserFlowService:
    """Возвращает singleton сервиса пользовательских черновиков."""

    global _user_flow_service
    if _user_flow_service is None:
        _user_flow_service = UserFlowService()
    return _user_flow_service


def get_ticket_link_service() -> TicketLinkService | PostgresTicketLinkService:
    """Возвращает сервис связи заявок с сообщениями MAX."""

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


def get_clarification_session_service() -> ClarificationSessionService:
    """Возвращает singleton сессий запроса уточнения."""

    global _clarification_session_service
    if _clarification_session_service is None:
        _clarification_session_service = ClarificationSessionService()
    return _clarification_session_service


def get_close_reply_session_service() -> CloseReplySessionService:
    """Возвращает singleton сессий закрытия с ответом."""

    global _close_reply_session_service
    if _close_reply_session_service is None:
        _close_reply_session_service = CloseReplySessionService()
    return _close_reply_session_service


def get_ticket_internal_comment_session_service() -> TicketInternalCommentSessionService:
    """Возвращает singleton сессий ввода внутренних комментариев."""

    global _ticket_internal_comment_session_service
    if _ticket_internal_comment_session_service is None:
        _ticket_internal_comment_session_service = TicketInternalCommentSessionService()
    return _ticket_internal_comment_session_service


def get_ticket_internal_comment_service() -> TicketInternalCommentService:
    """Возвращает сервис внутренних комментариев по заявкам."""

    global _ticket_internal_comment_service
    if _ticket_internal_comment_service is None:
        cfg = get_config()
        repository = None
        if cfg.tickets.backend == "postgres":
            from app.helpdesk.repositories.postgres_ticket_context_repository import (
                PostgresTicketContextRepository,
            )

            repository = PostgresTicketContextRepository(
                host=cfg.tickets.postgres_host,
                port=cfg.tickets.postgres_port,
                database=cfg.tickets.postgres_db,
                user=cfg.tickets.postgres_user,
                password=cfg.tickets.postgres_password,
                sslmode=cfg.tickets.postgres_sslmode,
                connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
            )
        _ticket_internal_comment_service = TicketInternalCommentService(
            repository,
            media_attachments=get_media_attachment_service(),
        )
    return _ticket_internal_comment_service


def get_knowledge_article_create_session_service() -> KnowledgeArticleCreateSessionService:
    """Возвращает singleton сессий ручного добавления KB-статей."""

    global _knowledge_article_create_session_service
    if _knowledge_article_create_session_service is None:
        _knowledge_article_create_session_service = KnowledgeArticleCreateSessionService()
    return _knowledge_article_create_session_service


def get_media_collection_session_service() -> MediaCollectionSessionService:
    """Возвращает singleton 15-секундного окна сбора media."""

    global _media_collection_session_service
    if _media_collection_session_service is None:
        cfg = get_config()
        _media_collection_session_service = MediaCollectionSessionService(
            collection_window_sec=cfg.media.collection_window_sec
        )
    return _media_collection_session_service


def get_media_attachment_service() -> MediaAttachmentService:
    """Возвращает сервис media metadata для PostgreSQL backend."""

    global _media_attachment_service
    if _media_attachment_service is not None:
        return _media_attachment_service

    cfg = get_config()
    repository = None
    if cfg.tickets.backend == "postgres":
        from app.helpdesk.repositories.postgres_media_attachment_repository import (
            PostgresMediaAttachmentRepository,
        )

        repository = PostgresMediaAttachmentRepository(
            host=cfg.tickets.postgres_host,
            port=cfg.tickets.postgres_port,
            database=cfg.tickets.postgres_db,
            user=cfg.tickets.postgres_user,
            password=cfg.tickets.postgres_password,
            sslmode=cfg.tickets.postgres_sslmode,
            connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
        )
    _media_attachment_service = MediaAttachmentService(
        repository=repository,
        max_attachments_per_item=cfg.media.max_attachments_per_item,
        max_file_size_mb=cfg.media.max_file_size_mb,
    )
    return _media_attachment_service


def get_ticket_clarification_service() -> TicketClarificationService:
    """Возвращает singleton последних уточнений для карточек заявок."""

    global _ticket_clarification_service
    if _ticket_clarification_service is None:
        cfg = get_config()
        repository = None
        if cfg.tickets.backend == "postgres":
            from app.helpdesk.repositories.postgres_ticket_context_repository import (
                PostgresTicketContextRepository,
            )

            repository = PostgresTicketContextRepository(
                host=cfg.tickets.postgres_host,
                port=cfg.tickets.postgres_port,
                database=cfg.tickets.postgres_db,
                user=cfg.tickets.postgres_user,
                password=cfg.tickets.postgres_password,
                sslmode=cfg.tickets.postgres_sslmode,
                connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
            )
        _ticket_clarification_service = TicketClarificationService(repository=repository)
    return _ticket_clarification_service


def get_knowledge_base_service() -> KnowledgeBaseService:
    """Возвращает singleton базы знаний для PostgreSQL backend."""

    global _knowledge_base_service
    if _knowledge_base_service is not None:
        return _knowledge_base_service

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        _knowledge_base_service = KnowledgeBaseService()
        return _knowledge_base_service

    from app.helpdesk.repositories.postgres_knowledge_base_repository import (
        PostgresKnowledgeBaseRepository,
    )
    from app.helpdesk.repositories.postgres_location_repository import (
        PostgresLocationRepository,
    )
    from app.helpdesk.repositories.postgres_ticket_context_repository import (
        PostgresTicketContextRepository,
    )
    from app.helpdesk.services.location_service import LocationService

    knowledge_repository = PostgresKnowledgeBaseRepository(
        host=cfg.tickets.postgres_host,
        port=cfg.tickets.postgres_port,
        database=cfg.tickets.postgres_db,
        user=cfg.tickets.postgres_user,
        password=cfg.tickets.postgres_password,
        sslmode=cfg.tickets.postgres_sslmode,
        connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
    )
    ticket_contexts = PostgresTicketContextRepository(
        host=cfg.tickets.postgres_host,
        port=cfg.tickets.postgres_port,
        database=cfg.tickets.postgres_db,
        user=cfg.tickets.postgres_user,
        password=cfg.tickets.postgres_password,
        sslmode=cfg.tickets.postgres_sslmode,
        connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
    )
    locations = LocationService(
        PostgresLocationRepository(
            host=cfg.tickets.postgres_host,
            port=cfg.tickets.postgres_port,
            database=cfg.tickets.postgres_db,
            user=cfg.tickets.postgres_user,
            password=cfg.tickets.postgres_password,
            sslmode=cfg.tickets.postgres_sslmode,
            connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
        )
    )
    _knowledge_base_service = KnowledgeBaseService(
        repository=knowledge_repository,
        ticket_contexts=ticket_contexts,
        locations=locations,
    )
    return _knowledge_base_service


def get_user_reply_session_service() -> UserReplySessionService:
    """Возвращает singleton сессий ответа пользователя."""

    global _user_reply_session_service
    if _user_reply_session_service is None:
        _user_reply_session_service = UserReplySessionService()
    return _user_reply_session_service


def get_user_addition_session_service() -> UserAdditionSessionService:
    """Возвращает singleton сессий пользовательского дополнения."""

    global _user_addition_session_service
    if _user_addition_session_service is None:
        _user_addition_session_service = UserAdditionSessionService()
    return _user_addition_session_service


def get_ticket_user_addition_service() -> TicketUserAdditionService:
    """Возвращает сервис пользовательских дополнений к заявкам."""

    global _ticket_user_addition_service
    if _ticket_user_addition_service is None:
        cfg = get_config()
        repository = None
        if cfg.tickets.backend == "postgres":
            from app.helpdesk.repositories.postgres_ticket_context_repository import (
                PostgresTicketContextRepository,
            )

            repository = PostgresTicketContextRepository(
                host=cfg.tickets.postgres_host,
                port=cfg.tickets.postgres_port,
                database=cfg.tickets.postgres_db,
                user=cfg.tickets.postgres_user,
                password=cfg.tickets.postgres_password,
                sslmode=cfg.tickets.postgres_sslmode,
                connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
            )
        _ticket_user_addition_service = TicketUserAdditionService(repository)
    return _ticket_user_addition_service


def get_room_ticket_context_service():
    """Возвращает сервис Jamaica room-ticket flow для PostgreSQL backend."""

    global _room_ticket_context_service
    if _room_ticket_context_service is not None:
        return _room_ticket_context_service

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        return None

    from app.helpdesk.repositories.postgres_location_repository import (
        PostgresLocationRepository,
    )
    from app.helpdesk.repositories.postgres_room_ticket_context_repository import (
        PostgresRoomTicketContextRepository,
    )
    from app.helpdesk.services.location_service import LocationService
    from app.helpdesk.services.room_ticket_context_service import (
        RoomTicketContextService,
    )

    location_repository = PostgresLocationRepository(
        host=cfg.tickets.postgres_host,
        port=cfg.tickets.postgres_port,
        database=cfg.tickets.postgres_db,
        user=cfg.tickets.postgres_user,
        password=cfg.tickets.postgres_password,
        sslmode=cfg.tickets.postgres_sslmode,
        connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
    )
    context_repository = PostgresRoomTicketContextRepository(
        host=cfg.tickets.postgres_host,
        port=cfg.tickets.postgres_port,
        database=cfg.tickets.postgres_db,
        user=cfg.tickets.postgres_user,
        password=cfg.tickets.postgres_password,
        sslmode=cfg.tickets.postgres_sslmode,
        connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
    )
    _room_ticket_context_service = RoomTicketContextService(
        locations=LocationService(location_repository),
        context_repository=context_repository,
    )
    return _room_ticket_context_service


def get_room_history_service() -> RoomHistoryService:
    """Возвращает singleton сервиса истории Jamaica room-ticket."""

    global _room_history_service
    if _room_history_service is not None:
        return _room_history_service

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        _room_history_service = RoomHistoryService()
        return _room_history_service

    from app.helpdesk.repositories.postgres_room_ticket_context_repository import (
        PostgresRoomTicketContextRepository,
    )

    repository = PostgresRoomTicketContextRepository(
        host=cfg.tickets.postgres_host,
        port=cfg.tickets.postgres_port,
        database=cfg.tickets.postgres_db,
        user=cfg.tickets.postgres_user,
        password=cfg.tickets.postgres_password,
        sslmode=cfg.tickets.postgres_sslmode,
        connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
    )
    _room_history_service = RoomHistoryService(repository=repository)
    return _room_history_service
