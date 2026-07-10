"""PostgreSQL-репозиторий базы знаний HelpDesk."""

from __future__ import annotations

import json
import threading
from typing import Any

from app.helpdesk.models.knowledge_base import (
    KnowledgeArticle,
    KnowledgeScope,
    KnowledgeScopeType,
)
from app.helpdesk.repositories.knowledge_base_repository import (
    CreateKnowledgeArticleInput,
)
from app.helpdesk.repositories.location_repository import IssueCategoryRef
from app.infrastructure.database.psycopg_connection import connect_postgres


class PostgresKnowledgeBaseRepository:
    """Работает с упрощенной таблицей helpdesk.knowledge_articles."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        sslmode: str = "prefer",
        connect_timeout_sec: int = 5,
    ) -> None:
        self._conninfo = (
            f"host={host} port={port} dbname={database} user={user} "
            f"password={password} sslmode={sslmode} connect_timeout={connect_timeout_sec}"
        )
        self._lock = threading.Lock()

    def _connect(self):
        try:
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL knowledge base repository requires psycopg."
            ) from exc
        return connect_postgres(self._conninfo, row_factory=dict_row)

    def create_article(self, payload: CreateKnowledgeArticleInput) -> KnowledgeArticle:
        """Создает статью базы знаний."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO helpdesk.knowledge_articles(
                        scope_id, hotel_id, category_id, title, body,
                        source_ticket_key, source_location_id, author_user_id,
                        is_active, sort_order, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s::jsonb
                    )
                    RETURNING *
                    """,
                    (
                        payload.scope_id,
                        payload.hotel_id,
                        payload.category_id,
                        payload.title,
                        payload.body,
                        payload.source_ticket_key,
                        payload.source_location_id,
                        payload.author_user_id,
                        payload.is_active,
                        payload.sort_order,
                        json.dumps(payload.metadata, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Could not create knowledge article")
        return self._article_from_row(row)

    def list_scopes(self) -> list[KnowledgeScope]:
        """Возвращает активные разделы базы знаний."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM helpdesk.knowledge_scopes
                    WHERE is_active = TRUE
                    ORDER BY sort_order ASC, id ASC
                    """
                )
                rows = cur.fetchall()
        return [self._scope_from_row(row) for row in rows]

    def get_scope(self, scope_id: int) -> KnowledgeScope | None:
        """Возвращает раздел базы знаний по ID."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM helpdesk.knowledge_scopes WHERE id = %s AND is_active = TRUE",
                    (scope_id,),
                )
                row = cur.fetchone()
        return self._scope_from_row(row) if row else None

    def get_scope_by_code(self, code: str) -> KnowledgeScope | None:
        """Возвращает раздел базы знаний по коду."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM helpdesk.knowledge_scopes
                    WHERE code = %s AND is_active = TRUE
                    LIMIT 1
                    """,
                    (code,),
                )
                row = cur.fetchone()
        return self._scope_from_row(row) if row else None

    def list_categories_for_scope(self, scope_id: int) -> tuple[IssueCategoryRef, ...]:
        """Возвращает категории для hotel-scope."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT hotel_id, scope_type
                    FROM helpdesk.knowledge_scopes
                    WHERE id = %s AND is_active = TRUE
                    LIMIT 1
                    """,
                    (scope_id,),
                )
                scope_row = cur.fetchone()
                if scope_row is None:
                    return ()
                if str(scope_row["scope_type"]) != KnowledgeScopeType.HOTEL.value:
                    return ()
                hotel_id = scope_row["hotel_id"]
                if hotel_id is None:
                    return ()
                cur.execute(
                    """
                    SELECT c.id, c.code, c.title, c.requires_location, hic.sort_order
                    FROM helpdesk.hotel_issue_categories hic
                    JOIN helpdesk.issue_categories c ON c.id = hic.category_id
                    WHERE hic.hotel_id = %s
                      AND hic.is_enabled = TRUE
                      AND c.is_active = TRUE
                    ORDER BY hic.sort_order, c.title
                    """,
                    (hotel_id,),
                )
                rows = cur.fetchall()
        return tuple(
            IssueCategoryRef(
                id=int(row["id"]),
                code=str(row["code"]),
                title=str(row["title"]),
                requires_location=bool(row["requires_location"]),
                sort_order=int(row["sort_order"]),
            )
            for row in rows
        )

    def get_article(self, article_id: int) -> KnowledgeArticle | None:
        """Возвращает статью по идентификатору."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM helpdesk.knowledge_articles
                    WHERE id = %s
                      AND is_active = TRUE
                    """,
                    (article_id,),
                )
                row = cur.fetchone()
        return self._article_from_row(row) if row else None

    def list_articles(
        self,
        *,
        scope_id: int,
        category_id: int,
        limit: int = 20,
    ) -> list[KnowledgeArticle]:
        """Возвращает активные статьи выбранной категории."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT *
                    FROM helpdesk.knowledge_articles
                    WHERE scope_id = %s
                      AND category_id = %s
                      AND is_active = TRUE
                    ORDER BY sort_order ASC,
                        created_at DESC,
                        id DESC
                    LIMIT %s
                    """,
                    (scope_id, category_id, limit),
                )
                rows = cur.fetchall()
        return [self._article_from_row(row) for row in rows]

    def _article_from_row(self, row: dict[str, Any]) -> KnowledgeArticle:
        return KnowledgeArticle(
            id=int(row["id"]),
            scope_id=int(row["scope_id"]),
            hotel_id=row.get("hotel_id"),
            category_id=int(row["category_id"]),
            title=str(row["title"]),
            body=str(row["body"]),
            source_ticket_key=row.get("source_ticket_key"),
            source_location_id=row.get("source_location_id"),
            author_user_id=row.get("author_user_id"),
            is_active=bool(row["is_active"]),
            sort_order=int(row.get("sort_order") or 0),
            metadata=dict(row.get("metadata") or {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _scope_from_row(self, row: dict[str, Any]) -> KnowledgeScope:
        return KnowledgeScope(
            id=int(row["id"]),
            code=str(row["code"]),
            title=str(row["title"]),
            scope_type=KnowledgeScopeType(str(row["scope_type"])),
            hotel_id=row.get("hotel_id"),
            is_active=bool(row["is_active"]),
            sort_order=int(row.get("sort_order") or 0),
            metadata=dict(row.get("metadata") or {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
