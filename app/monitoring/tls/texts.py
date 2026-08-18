"""Тексты напоминания об окончании TLS-сертификата."""

from datetime import datetime


def render_tls_reminder(
    *,
    host: str,
    not_after: datetime,
    remaining_days: int,
    server_hint: str = "",
    expired: bool = False,
) -> str:
    """Формирует сообщение без технических данных сертификата."""

    server_text = (
        f" на сервер {server_hint}" if server_hint.strip() else " для MAX-бота"
    )
    instruction = (
        "Для автоматического продления Let's Encrypt необходимо временно "
        f"открыть внешний TCP/80{server_text}."
    )
    if expired:
        return (
            f"⚠️ TLS-сертификат {host} уже истёк.\n\n"
            f"Срок действия: {not_after:%d.%m.%Y}\n\n"
            f"{instruction}\n\n"
            "После открытия порта проверьте продление сертификата."
        )

    return (
        "⚠️ Сертификат MAX-бота скоро истекает\n\n"
        f"Домен: {host}\n"
        f"Срок действия: {not_after:%d.%m.%Y}\n"
        f"Осталось: {remaining_days} {_day_word(remaining_days)}\n\n"
        f"{instruction}\n\n"
        "После открытия порта проверьте продление сертификата."
    )


def _day_word(days: int) -> str:
    absolute = abs(days)
    if absolute % 10 == 1 and absolute % 100 != 11:
        return "день"
    if absolute % 10 in {2, 3, 4} and absolute % 100 not in {12, 13, 14}:
        return "дня"
    return "дней"
