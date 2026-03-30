from typing import Any


def get_first_name(user: Any, fallback: str) -> str:
    first_name = getattr(user, "first_name", None)
    if first_name:
        return str(first_name)
    return fallback


def get_full_name(user: Any, fallback: str) -> str:
    first_name = getattr(user, "first_name", "") or ""
    last_name = getattr(user, "last_name", "") or ""
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name

    display_name = getattr(user, "name", None)
    if display_name:
        return str(display_name)

    return fallback

