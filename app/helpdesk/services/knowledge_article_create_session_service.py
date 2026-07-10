"""Runtime-сессии ручного добавления статей в базу знаний."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass(slots=True)
class KnowledgeArticleCreateSession:
    """Состояние мастера ручного создания статьи KB."""

    actor_user_id: int
    chat_id: int | None
    hotel_id: int | None
    scope_id: int | None
    scope_code: str | None
    scope_title: str | None
    category_id: int | None
    category_code: str | None
    category_title: str | None
    step: str
    started_at: datetime
    title: str = ""
    prompt_message_id: str | None = None
    session_id: str = ""


class KnowledgeArticleCreateSessionService:
    """Хранит активные сессии ручного добавления статей KB."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[int, KnowledgeArticleCreateSession] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def start(
        self,
        *,
        actor_user_id: int,
        chat_id: int | None = None,
        hotel_id: int | None = None,
        scope_id: int | None = None,
        scope_code: str | None = None,
        scope_title: str | None = None,
        category_id: int | None = None,
        category_code: str | None = None,
        category_title: str | None = None,
    ) -> KnowledgeArticleCreateSession:
        """Создает новую сессию ручного добавления статьи."""

        if scope_id is None:
            step = "waiting_scope"
        elif category_id is None:
            step = "waiting_category"
        else:
            step = "waiting_title"
        session = KnowledgeArticleCreateSession(
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            hotel_id=hotel_id,
            scope_id=scope_id,
            scope_code=scope_code,
            scope_title=scope_title,
            category_id=category_id,
            category_code=category_code,
            category_title=category_title,
            step=step,
            started_at=datetime.now(tz=timezone.utc),
            session_id=uuid4().hex,
        )
        self._sessions[actor_user_id] = session
        return session

    def get(self, actor_user_id: int) -> KnowledgeArticleCreateSession | None:
        """Возвращает активную сессию пользователя."""

        self.cleanup_expired()
        return self._sessions.get(actor_user_id)

    def set_prompt_message_id(self, actor_user_id: int, prompt_message_id: str | None) -> None:
        """Сохраняет ID последнего prompt-сообщения."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return
        session.prompt_message_id = str(prompt_message_id) if prompt_message_id else None

    def set_scope(
        self,
        actor_user_id: int,
        *,
        scope_id: int,
        scope_code: str,
        scope_title: str,
        hotel_id: int | None,
    ) -> KnowledgeArticleCreateSession | None:
        """Привязывает раздел и переводит к выбору категории."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return None
        session.scope_id = scope_id
        session.scope_code = scope_code
        session.scope_title = scope_title
        session.hotel_id = hotel_id
        session.step = "waiting_category"
        return session

    def set_category(
        self,
        actor_user_id: int,
        *,
        category_id: int,
        category_code: str,
        category_title: str,
    ) -> KnowledgeArticleCreateSession | None:
        """Привязывает категорию и переводит к вводу заголовка."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return None
        session.category_id = category_id
        session.category_code = category_code
        session.category_title = category_title
        session.step = "waiting_title"
        return session

    def set_title(self, actor_user_id: int, title: str) -> KnowledgeArticleCreateSession | None:
        """Сохраняет заголовок и переводит к вводу текста."""

        session = self._sessions.get(actor_user_id)
        if session is None:
            return None
        session.title = title
        session.step = "waiting_body"
        return session

    def finish(self, actor_user_id: int) -> KnowledgeArticleCreateSession | None:
        """Завершает сессию добавления статьи."""

        return self._sessions.pop(actor_user_id, None)

    def reset(self, actor_user_id: int) -> None:
        """Сбрасывает активную сессию."""

        self._sessions.pop(actor_user_id, None)

    def cleanup_expired(self) -> int:
        """Удаляет устаревшие сессии."""

        now = datetime.now(tz=timezone.utc)
        expired_ids = [
            actor_id
            for actor_id, session in self._sessions.items()
            if now - session.started_at > self._ttl
        ]
        for actor_id in expired_ids:
            self._sessions.pop(actor_id, None)
        return len(expired_ids)
