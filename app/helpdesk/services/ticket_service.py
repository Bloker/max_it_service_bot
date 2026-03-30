from typing import Any

from app.common.user_helpers import get_full_name


def get_sender_identity(sender: Any, fallback_name: str) -> tuple[int, str]:
    sender_id = int(getattr(sender, "user_id"))
    full_name = get_full_name(sender, fallback=fallback_name)
    return sender_id, full_name


def normalize_ticket_text(raw_text: str | None, empty_text_fallback: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return empty_text_fallback
    return text


def is_command_text(text: str) -> bool:
    return text.startswith("/")


def get_message_attachments(body: Any) -> list[Any]:
    return list(getattr(body, "attachments", None) or [])


def get_optional_contact_details(sender: Any) -> tuple[str | None, str | None]:
    phone = getattr(sender, "phone", None)
    department = getattr(sender, "department", None)
    return (
        str(phone).strip() if phone else None,
        str(department).strip() if department else None,
    )


def normalize_ticket_id(raw: str) -> str:
    return raw.strip().upper()


def parse_specialist_command(raw_text: str) -> tuple[str, str | None]:
    parts = (raw_text or "").strip().split(maxsplit=1)
    if not parts:
        return "", None

    cmd = parts[0].lower().lstrip("/")
    ticket_id = normalize_ticket_id(parts[1]) if len(parts) > 1 else None
    if cmd not in {"take", "release", "close", "clarify"}:
        return "", None
    return cmd, ticket_id

