"""Фильтрация и нормализация вложений для HelpDesk flow."""

from typing import Any

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload
from maxapi.types.attachments.audio import Audio


TICKET_MEDIA_ATTACHMENT_MARKERS = (
    "image",
    "photo",
    "video",
    "file",
    "document",
    "audio",
    "audio_message",
    "audiomessage",
    "voice",
    "voice_message",
    "voice_note",
    "audiomsg",
    "ptt",
    "sound",
)
NON_FORWARDABLE_ATTACHMENT_MARKERS = (
    "contact",
    "inline_keyboard",
    "reply_keyboard",
    "button",
    "sticker",
)
UPLOAD_ATTACHMENT_TYPE_ALIASES = {
    "photo": "image",
    "document": "file",
    "voice": "audio",
    "voice_message": "audio",
    "audiomsg": "audio",
}
UPLOAD_ATTACHMENT_TYPES = {"image", "video", "audio", "file"}
AUDIO_ATTACHMENT_MARKERS = (
    "audio",
    "voice",
    "voice_message",
    "voice_note",
    "audiomsg",
    "audiomessage",
    "ptt",
    "sound",
)
AUDIO_URL_MARKERS = (
    "audio",
    "voice",
    ".ogg",
    ".oga",
    ".opus",
    ".mp3",
    ".m4a",
    ".aac",
    ".amr",
    ".wav",
)
AUDIO_METADATA_FIELDS = (
    "filename",
    "file_name",
    "name",
    "mime_type",
    "content_type",
    "media_type",
    "transcription",
)
PRIVATE_PAYLOAD_FIELDS = {"url", "token"}


def _attachment_type(attachment: Any) -> str:
    """Возвращает тип вложения в нижнем регистре."""

    return str(getattr(attachment, "type", "")).lower()


def _normalize_upload_type(attachment_type: str) -> str:
    """Приводит клиентские алиасы MAX к типам upload API."""

    normalized = UPLOAD_ATTACHMENT_TYPE_ALIASES.get(attachment_type, attachment_type)
    if normalized in UPLOAD_ATTACHMENT_TYPES:
        return normalized
    for marker, upload_type in UPLOAD_ATTACHMENT_TYPE_ALIASES.items():
        if marker in attachment_type:
            return upload_type
    for upload_type in UPLOAD_ATTACHMENT_TYPES:
        if upload_type in attachment_type:
            return upload_type
    return normalized


def _get_payload_value(attachment: Any, name: str) -> Any:
    """Достаёт значение из payload независимо от модели MAX."""

    payload = getattr(attachment, "payload", None)
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(name)
    return getattr(payload, name, None)


def _payload_field_names(attachment: Any) -> list[str]:
    """Возвращает имена полей payload без значений приватных URL/token."""

    payload = getattr(attachment, "payload", None)
    if payload is None:
        return []
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())
    if hasattr(payload, "model_fields"):
        return sorted(str(key) for key in payload.model_fields.keys())
    if hasattr(payload, "__dict__"):
        return sorted(str(key) for key in payload.__dict__.keys())
    return []


def _get_public_metadata_value(attachment: Any, name: str) -> str | None:
    """Достаёт непубличную для логов metadata без URL/token."""

    value = getattr(attachment, name, None)
    if value is None:
        value = _get_payload_value(attachment, name)
    if value is None:
        return None
    return str(value)


def _audio_detection_haystack(attachment: Any) -> str:
    """Собирает безопасные признаки audio/voice без URL/token."""

    parts = [
        attachment.__class__.__name__,
        _attachment_type(attachment),
    ]
    payload = getattr(attachment, "payload", None)
    if payload is not None:
        parts.append(payload.__class__.__name__)
    for field_name in AUDIO_METADATA_FIELDS:
        value = _get_public_metadata_value(attachment, field_name)
        if value:
            parts.append(value)
    parts.extend(_payload_field_names(attachment))
    return " ".join(parts).lower()


def get_attachment_token(attachment: Any) -> str | None:
    """Достаёт upload token из вложения или его payload."""

    token = getattr(attachment, "token", None) or _get_payload_value(attachment, "token")
    return str(token) if token else None


def get_attachment_url(attachment: Any) -> str | None:
    """Достаёт URL вложения без логирования приватного значения."""

    url = getattr(attachment, "url", None) or _get_payload_value(attachment, "url")
    return str(url) if url else None


def _has_attachment_url(attachment: Any) -> bool:
    """Проверяет наличие URL без вывода самого URL в логи."""

    return bool(get_attachment_url(attachment))


def summarize_attachment(attachment: Any) -> str:
    """Формирует безопасную сводку вложения для логов без token/url."""

    payload = getattr(attachment, "payload", None)
    payload_fields = [
        field_name
        for field_name in _payload_field_names(attachment)
        if field_name not in PRIVATE_PAYLOAD_FIELDS
    ]
    return (
        f"{attachment.__class__.__name__}("
        f"type={_attachment_type(attachment) or '-'}, "
        f"payload={payload.__class__.__name__ if payload is not None else '-'}, "
        f"payload_fields={payload_fields}, "
        f"has_token={bool(get_attachment_token(attachment))}, "
        f"has_url={_has_attachment_url(attachment)}, "
        f"is_audio={is_audio_attachment(attachment)})"
    )


def is_ticket_media_attachment(attachment: Any) -> bool:
    """Проверяет, можно ли переслать вложение в HelpDesk flow."""

    att_type = _attachment_type(attachment)
    if any(marker in att_type for marker in NON_FORWARDABLE_ATTACHMENT_MARKERS):
        return False
    if is_audio_attachment(attachment):
        return True
    return any(marker in att_type for marker in TICKET_MEDIA_ATTACHMENT_MARKERS)


def is_audio_attachment(attachment: Any) -> bool:
    """Проверяет audio/voice-вложение по типу модели и строковым алиасам MAX."""

    if isinstance(attachment, Audio):
        return True
    haystack = _audio_detection_haystack(attachment)
    if any(marker in haystack for marker in AUDIO_ATTACHMENT_MARKERS):
        return True
    url = get_attachment_url(attachment)
    if url:
        normalized_url = url.split("?", 1)[0].lower()
        if any(marker in normalized_url for marker in AUDIO_URL_MARKERS):
            return True
    upload_type = _normalize_upload_type(_attachment_type(attachment))
    return upload_type == "audio"


def normalize_ticket_media_attachment(attachment: Any) -> Any | None:
    """Готовит входящее media-вложение к повторной отправке через MAX API."""

    if not is_ticket_media_attachment(attachment):
        return None

    upload_type = _normalize_upload_type(_attachment_type(attachment))
    token = get_attachment_token(attachment)
    if upload_type in UPLOAD_ATTACHMENT_TYPES and token:
        return AttachmentUpload(
            type=UploadType(upload_type),
            payload=AttachmentPayload(token=token),
        )
    return attachment


def collect_ticket_media_attachments(
    attachments: list[Any],
    *,
    include_audio: bool = True,
) -> list[Any]:
    """Отбирает вложения, которые можно прикреплять к заявкам."""

    normalized: list[Any] = []
    for attachment in attachments:
        if not include_audio and is_audio_attachment(attachment):
            continue
        media_attachment = normalize_ticket_media_attachment(attachment)
        if media_attachment is not None:
            normalized.append(media_attachment)
    return normalized
