"""Контракты persistent-хранилища media-вложений."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.helpdesk.models.media_attachment import MediaAttachment


@dataclass(slots=True, frozen=True)
class CreateMediaAttachmentInput:
    """Входные данные для сохранения media-вложения."""

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


class MediaAttachmentRepository(Protocol):
    """Контракт репозитория media-вложений."""

    def create_attachment(self, payload: CreateMediaAttachmentInput) -> MediaAttachment: ...

    def list_attachments(self, *, owner_type: str, owner_id: int) -> list[MediaAttachment]: ...
