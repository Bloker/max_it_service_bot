def get_helpdesk_commands() -> tuple[str, ...]:
    return ("/start", "/menu", "/my", "/network", "/help")


def get_ticket_categories() -> list[str]:
    return [
        "Доступы и учетные записи",
        "ПК и программное обеспечение",
        "Принтеры",
        "Сеть / Wi-Fi",
        "VPN",
        "Телефония",
        "Прочее",
    ]
