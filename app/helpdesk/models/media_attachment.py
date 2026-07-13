"""Доменные модели media-вложений HelpDesk."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


MEDIA_OWNER_TICKET_COMMENT = "ticket_comment"
MEDIA_OWNER_KNOWLEDGE_ARTICLE = "knowledge_article"
MEDIA_SUPPORTED_OWNER_TYPES = {
    MEDIA_OWNER_TICKET_COMMENT,
    MEDIA_OWNER_KNOWLEDGE_ARTICLE,
}
MEDIA_SUPPORTED_TYPES = {"photo", "video", "document"}


@dataclass(slots=True, frozen=True)
class MediaAttachment:
    """Сохранённое media-вложение комментария или KB-статьи."""

    id: int
    owner_type: str
    owner_id: int | None
    ticket_key: str | None
    hotel_id: int | None
    location_id: int | None
    media_type: str
    mime_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    max_file_id: str | None = None
    max_attachment_id: str | None = None
    storage_path: str | None = None
    public_url: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_by: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass(slots=True, frozen=True)
class MediaAttachmentCounts:
    """Счётчики вложений по типам."""

    photo_count: int = 0
    video_count: int = 0
    document_count: int = 0

    @property
    def total_count(self) -> int:
        return self.photo_count + self.video_count + self.document_count
