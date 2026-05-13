"""Валидация пользовательского target для сетевых инструментов."""

import ipaddress
import re


HOST_RE = re.compile(r"^(?=.{1,253}$)(?!-)[a-zA-Z0-9.-]+(?<!-)$")


def normalize_target(raw: str) -> str:
    """Нормализует введенный адрес для дальнейшей проверки."""

    return (raw or "").strip().lower()


def validate_target_format(target: str, max_length: int = 253) -> tuple[bool, str]:
    """Проверяет базовый формат IP-адреса или hostname."""

    if not target:
        return False, "Укажите хост или IP."
    if len(target) > max_length:
        return False, "Адрес слишком длинный."

    try:
        ipaddress.ip_address(target)
        return True, ""
    except ValueError:
        pass

    if not HOST_RE.match(target):
        return False, "Некорректный формат адреса."
    if ".." in target:
        return False, "Некорректный формат адреса."
    return True, ""
