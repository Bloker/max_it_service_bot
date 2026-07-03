"""Общие formatter-утилиты HelpDesk-текстов."""

import re


_DIGITS_RE = re.compile(r"\D+")


def format_ru_phone(phone: str | None) -> str:
    """Нормализует российский телефон для отображения в карточке."""

    if not phone:
        return "не указан"

    digits = _DIGITS_RE.sub("", str(phone))
    if len(digits) == 11 and digits.startswith("8"):
        return f"+7{digits[1:]}"
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+7{digits}"
    return "не указан"
