"""Сервис сохранения и чтения media-вложений."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload

from app.helpdesk.models.media_attachment import (
    MEDIA_SUPPORTED_OWNER_TYPES,
    MEDIA_SUPPORTED_TYPES,
    MediaAttachment,
    MediaAttachmentCounts,
)
from app.helpdesk.repositories.media_attachment_repository import (
    CreateMediaAttachmentInput,
    MediaAttachmentRepository,
)
from app.helpdesk.services.attachment_filter_service import get_attachment_token, is_audio_attachment


@dataclass(slots=True, frozen=True)
class MediaCollectResult:
    """Результат обработки входящего вложения."""

    accepted: list[Any]
    rejected_messages: list[str]


class MediaAttachmentService:
    """Работает с metadata вложений без хранения binary в PostgreSQL."""

    def __init__(
        self,
        repository: MediaAttachmentRepository | None = None,
        *,
        max_attachments_per_item: int = 10,
        max_file_size_mb: int = 50,
    ) -> None:
        self._repository = repository
        self._max_attachments_per_item = max_attachments_per_item
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def collect_supported(
        self,
        existing_count: int,
        attachments: list[Any] | None,
    ) -> MediaCollectResult:
        """Фильтрует и валидирует поддерживаемые вложения."""

        accepted: list[Any] = []
        rejected: list[str] = []
        for attachment in attachments or []:
            media_type = _resolve_media_type(attachment)
            if media_type is None:
                rejected.append("Этот тип вложения пока не поддерживается.")
                continue
            if media_type in {"audio", "voice"}:
                rejected.append("Аудио и голосовые пока не поддерживаются.")
                continue
            if existing_count + len(accepted) >= self._max_attachments_per_item:
                rejected.append("Вложение не добавлено: превышен лимит.")
                continue
            file_size = _first_attachment_value(attachment, ("size", "file_size"))
            if isinstance(file_size, str) and file_size.isdigit():
                file_size = int(file_size)
            if isinstance(file_size, (int, float)) and int(file_size) > self._max_file_size_bytes:
                rejected.append("Вложение не добавлено: превышен лимит.")
                continue
            accepted.append(attachment)
        return MediaCollectResult(accepted=accepted, rejected_messages=rejected)

    def save_many(
        self,
        *,
        owner_type: str,
        owner_id: int,
        ticket_key: str | None,
        hotel_id: int | None,
        location_id: int | None,
        attachments: list[Any],
        created_by: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> list[MediaAttachment]:
        """Сохраняет список вложений владельца."""

        if owner_type not in MEDIA_SUPPORTED_OWNER_TYPES:
            raise ValueError("Unsupported owner_type")
        saved: list[MediaAttachment] = []
        for order, attachment in enumerate(attachments, start=1):
            media_type = _resolve_media_type(attachment)
            # Защита второго уровня: обработчики уже фильтруют audio/voice,
            # но прямой вызов сервиса не должен обойти ограничения MVP.
            if media_type not in MEDIA_SUPPORTED_TYPES:
                continue
            item_metadata = dict(metadata or {})
            item_metadata.update(_build_attachment_metadata(attachment, order=order, media_type=media_type))
            payload = CreateMediaAttachmentInput(
                owner_type=owner_type,
                owner_id=owner_id,
                ticket_key=ticket_key,
                hotel_id=hotel_id,
                location_id=location_id,
                media_type=media_type,
                mime_type=_string_or_none(_first_attachment_value(attachment, ("content_type", "mime_type", "media_type"))),
                file_name=_string_or_none(_first_attachment_value(attachment, ("filename", "file_name", "name"))),
                file_size=_int_or_none(_first_attachment_value(attachment, ("size", "file_size"))),
                max_file_id=_string_or_none(_first_attachment_value(attachment, ("file_id", "max_file_id"))),
                max_attachment_id=_string_or_none(_first_attachment_value(attachment, ("attachment_id", "max_attachment_id", "id"))),
                storage_path=None,
                public_url=None,
                checksum=None,
                metadata=item_metadata,
                created_by=created_by,
            )
            if self._repository is None:
                saved.append(
                    MediaAttachment(
                        id=len(saved) + 1,
                        owner_type=payload.owner_type,
                        owner_id=payload.owner_id,
                        ticket_key=payload.ticket_key,
                        hotel_id=payload.hotel_id,
                        location_id=payload.location_id,
                        media_type=payload.media_type,
                        mime_type=payload.mime_type,
                        file_name=payload.file_name,
                        file_size=payload.file_size,
                        max_file_id=payload.max_file_id,
                        max_attachment_id=payload.max_attachment_id,
                        storage_path=payload.storage_path,
                        public_url=payload.public_url,
                        checksum=payload.checksum,
                        metadata=payload.metadata,
                        created_by=payload.created_by,
                    )
                )
                continue
            saved.append(self._repository.create_attachment(payload))
        return saved

    def list_attachments(self, *, owner_type: str, owner_id: int) -> list[MediaAttachment]:
        """Возвращает список вложений владельца."""

        if owner_type not in MEDIA_SUPPORTED_OWNER_TYPES or self._repository is None:
            return []
        return self._repository.list_attachments(owner_type=owner_type, owner_id=owner_id)

    def count_attachments(self, *, owner_type: str, owner_id: int) -> MediaAttachmentCounts:
        """Считает вложения по типам."""

        data = {
            "photo_count": 0,
            "video_count": 0,
            "document_count": 0,
        }
        for attachment in self.list_attachments(owner_type=owner_type, owner_id=owner_id):
            key = f"{attachment.media_type}_count"
            if key not in data:
                continue
            data[key] += 1
        return MediaAttachmentCounts(**data)

    def build_upload_attachments(self, *, owner_type: str, owner_id: int) -> list[Any]:
        """Готовит MAX-вложения для повторной отправки по token."""

        uploads: list[Any] = []
        for item in self.list_attachments(owner_type=owner_type, owner_id=owner_id):
            token = item.max_file_id or item.max_attachment_id or item.metadata.get("token")
            if not token:
                continue
            upload_type = _upload_type_for_media(item.media_type)
            if upload_type is None:
                continue
            uploads.append(
                AttachmentUpload(
                    type=upload_type,
                    payload=AttachmentPayload(token=str(token)),
                )
            )
        return uploads


def _build_attachment_metadata(attachment: Any, *, order: int, media_type: str) -> dict[str, Any]:
    metadata = {
        "order": order,
        "type": media_type,
        "has_token": bool(get_attachment_token(attachment)),
        "is_audio": is_audio_attachment(attachment),
    }
    token = get_attachment_token(attachment)
    if token:
        metadata["token"] = token
    attachment_id = _first_attachment_value(attachment, ("attachment_id", "max_attachment_id", "id"))
    if attachment_id is not None:
        metadata["attachment_id"] = str(attachment_id)
    return metadata


def _resolve_media_type(attachment: Any) -> str | None:
    raw_type = str(getattr(attachment, "type", "") or "").lower()
    if is_audio_attachment(attachment):
        if "voice" in raw_type or "ptt" in raw_type or "audiomsg" in raw_type:
            return "voice"
        return "audio"
    if raw_type in {"photo", "image"}:
        return "photo"
    if "video" in raw_type:
        return "video"
    if raw_type in {"file", "document"}:
        return "document"
    return None


def _first_attachment_value(attachment: Any, field_names: tuple[str, ...]) -> Any:
    payload = getattr(attachment, "payload", None)
    for field_name in field_names:
        value = getattr(attachment, field_name, None)
        if value is not None:
            return value
        if isinstance(payload, dict):
            value = payload.get(field_name)
        elif payload is not None:
            value = getattr(payload, field_name, None)
        if value is not None:
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value not in {None, ""} else None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _upload_type_for_media(media_type: str) -> UploadType | None:
    if media_type == "photo":
        return UploadType.IMAGE
    if media_type == "video":
        return UploadType.VIDEO
    if media_type == "document":
        return UploadType.FILE
    return None
