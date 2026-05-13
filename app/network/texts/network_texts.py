"""Тексты раздела сетевых инструментов."""

NETWORK_MENU_TEXT = (
    "Сетевые инструменты (доступ: админ/IT).\n"
    "Выберите инструмент диагностики."
)

NO_ACCESS_TEXT = "Нет доступа к сетевым инструментам."

WIFI_ROOM_PROMPT_TEXT = "Введите номер комнаты для поиска последнего WiFi-ваучера."

PROMPT_BY_TOOL: dict[str, str] = {
    "ping": "Введите корпоративный хост/IP для ping.",
    "dns": "Введите корпоративный хост для DNS lookup.",
    "traceroute": "Введите корпоративный хост/IP для traceroute.",
    "nslookup": "Введите корпоративный хост для nslookup.",
    "whois": "Введите корпоративный хост для whois.",
}

UNKNOWN_TOOL_TEXT = "Инструмент пока не поддерживается."


def render_result(title: str, ok: bool, details: str) -> str:
    """Форматирует результат сетевой диагностики для MAX-сообщения."""

    status = "OK" if ok else "ERROR"
    return f"[{status}] {title}\n{details}"
