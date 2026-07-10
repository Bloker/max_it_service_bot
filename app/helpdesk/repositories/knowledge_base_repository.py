"""Контракты репозитория базы знаний HelpDesk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.helpdesk.models.knowledge_base import (
    KnowledgeArticle,
    KnowledgeScope,
)
from app.helpdesk.repositories.location_repository import IssueCategoryRef


@dataclass(slots=True, frozen=True)
class CreateKnowledgeArticleInput:
    """Данные для создания статьи базы знаний."""

    scope_id: int
    hotel_id: int | None
    category_id: int
    title: str
    body: str
    source_ticket_key: str | None = None
    source_location_id: int | None = None
    author_user_id: int | None = None
    is_active: bool = True
    sort_order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeBaseRepository(Protocol):
    """Контракт persistent-хранилища базы знаний."""

    def list_scopes(self) -> list[KnowledgeScope]: ...

    def get_scope(self, scope_id: int) -> KnowledgeScope | None: ...

    def get_scope_by_code(self, code: str) -> KnowledgeScope | None: ...

    def list_categories_for_scope(self, scope_id: int) -> tuple[IssueCategoryRef, ...]: ...

    def create_article(self, payload: CreateKnowledgeArticleInput) -> KnowledgeArticle: ...

    def get_article(self, article_id: int) -> KnowledgeArticle | None: ...

    def list_articles(
        self,
        *,
        scope_id: int,
        category_id: int,
        limit: int = 20,
    ) -> list[KnowledgeArticle]: ...
