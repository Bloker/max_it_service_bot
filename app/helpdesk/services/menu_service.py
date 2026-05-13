"""Статические списки команд и категорий HelpDesk."""


def get_helpdesk_commands() -> tuple[str, ...]:
    """Возвращает список slash-команд HelpDesk."""

    return (
        "/start",
        "/menu",
        "/my",
        "/network",
        "/group",
        "/register",
        "/pending",
        "/approve <user_id> [user|it|admin]",
        "/users",
        "/ban <user_id>",
        "/delete_user <user_id>",
        "/help",
    )


def get_ticket_categories() -> list[str]:
    """Возвращает список категорий заявок."""

    return [
        "Доступы и учетные записи",
        "ПК и программное обеспечение",
        "Принтеры",
        "Сеть / Wi-Fi",
        "VPN",
        "Телефония",
        "Прочее",
    ]
