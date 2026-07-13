"""PostgreSQL-репозиторий media-вложений HelpDesk."""

from __future__ import annotations

import json
import threading
from typing import Any

from app.helpdesk.models.media_attachment import MediaAttachment
from app.helpdesk.repositories.media_attachment_repository import CreateMediaAttachmentInput
from app.infrastructure.database.psycopg_connection import connect_postgres


class PostgresMediaAttachmentRepository:
    """Работает с таблицей helpdesk.media_attachments."""

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
            raise RuntimeError("PostgreSQL media repository requires psycopg.") from exc
        return connect_postgres(self._conninfo, row_factory=dict_row)

    def create_attachment(self, payload: CreateMediaAttachmentInput) -> MediaAttachment:
        """Сохраняет media-вложение."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO helpdesk.media_attachments(
                        owner_type, owner_id, ticket_key, hotel_id, location_id,
                        media_type, mime_type, file_name, file_size,
                        max_file_id, max_attachment_id, storage_path,
                        public_url, checksum, metadata, created_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s::jsonb, %s
                    )
                    RETURNING *
                    """,
                    (
                        payload.owner_type,
                        payload.owner_id,
                        payload.ticket_key,
                        payload.hotel_id,
                        payload.location_id,
                        payload.media_type,
                        payload.mime_type,
                        payload.file_name,
                        payload.file_size,
                        payload.max_file_id,
                        payload.max_attachment_id,
                        payload.storage_path,
                        payload.public_url,
                        payload.checksum,
                        json.dumps(payload.metadata, ensure_ascii=False),
                        payload.created_by,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Could not create media attachment")
        return self._from_row(row)

    def list_attachments(self, *, owner_type: str, owner_id: int) -> list[MediaAttachment]:
        """Возвращает все вложения владельца."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM helpdesk.media_attachments
                    WHERE owner_type = %s
                      AND owner_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (owner_type, owner_id),
                )
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: dict[str, Any]) -> MediaAttachment:
        return MediaAttachment(
            id=int(row["id"]),
            owner_type=str(row["owner_type"]),
            owner_id=int(row["owner_id"]) if row.get("owner_id") is not None else None,
            ticket_key=row.get("ticket_key"),
            hotel_id=int(row["hotel_id"]) if row.get("hotel_id") is not None else None,
            location_id=int(row["location_id"]) if row.get("location_id") is not None else None,
            media_type=str(row["media_type"]),
            mime_type=row.get("mime_type"),
            file_name=row.get("file_name"),
            file_size=int(row["file_size"]) if row.get("file_size") is not None else None,
            max_file_id=row.get("max_file_id"),
            max_attachment_id=row.get("max_attachment_id"),
            storage_path=row.get("storage_path"),
            public_url=row.get("public_url"),
            checksum=row.get("checksum"),
            metadata=dict(row.get("metadata") or {}),
            created_by=int(row["created_by"]) if row.get("created_by") is not None else None,
            created_at=row["created_at"],
        )
