"""Фабрики inline-клавиатур пользовательского и IT-меню."""

from maxapi.types import ButtonsPayload, CallbackButton, RequestContactButton

from app.helpdesk.payloads import SpecialistTicketPayload, UserMenuPayload


def build_main_menu_keyboard(
    *,
    can_create_ticket: bool = True,
    can_view_my_tickets: bool = True,
    can_view_help: bool = True,
    can_view_about: bool = False,
    can_use_network_tools: bool = False,
    can_view_service_functions: bool = False,
    is_admin: bool = False,
    can_use_wifi_help: bool = False,
    can_use_tv_help: bool = False,
):
    """Собирает главное меню с учетом роли и доступных функций."""

    if can_use_wifi_help:
        buttons = [
            [CallbackButton(text="Проблема Wi-Fi у гостя", payload=UserMenuPayload(action="wifi").pack())],
        ]
    else:
        buttons = []

    # Временно скрыто до подготовки дорожной карты по TV-инцидентам.
    # if can_use_tv_help:
    #     buttons.append(
    #         [CallbackButton(text="Проблема с TV у гостя", payload=UserMenuPayload(action="tv_guest").pack())]
    #     )

    if can_create_ticket:
        buttons.append(
            [CallbackButton(text="Создать обращение", payload=UserMenuPayload(action="create").pack())]
        )

    if can_view_my_tickets:
        buttons.append([CallbackButton(text="Мои обращения", payload=UserMenuPayload(action="my").pack())])

    info_buttons: list[CallbackButton] = []
    if can_view_help:
        info_buttons.append(CallbackButton(text="Помощь", payload=UserMenuPayload(action="help").pack()))
    if can_view_about:
        info_buttons.append(CallbackButton(text="О боте", payload=UserMenuPayload(action="about").pack()))
    if info_buttons:
        buttons.append(info_buttons)

    if can_use_network_tools:
        buttons.append(
            [
                CallbackButton(
                    text="Сетевые инструменты",
                    payload=UserMenuPayload(action="network").pack(),
                )
            ]
        )

    if is_admin:
        buttons.append(
            [
                CallbackButton(
                    text="Права администратора",
                    payload=UserMenuPayload(action="admin_help").pack(),
                )
            ]
        )

    return ButtonsPayload(buttons=buttons).pack()


def build_categories_keyboard(categories: list[str]):
    """Собирает клавиатуру выбора категории заявки."""

    rows = [
        [CallbackButton(text=category, payload=UserMenuPayload(action="cat", value=category).pack())]
        for category in categories
    ]
    rows.append([CallbackButton(text="Назад", payload=UserMenuPayload(action="menu").pack())])
    return ButtonsPayload(buttons=rows).pack()


def build_confirm_keyboard():
    """Собирает клавиатуру подтверждения черновика заявки."""

    return ButtonsPayload(
        buttons=[
            [CallbackButton(text="Отправить", payload=UserMenuPayload(action="confirm_send").pack())],
            [CallbackButton(text="Изменить текст", payload=UserMenuPayload(action="rewrite").pack())],
            [CallbackButton(text="Отмена", payload=UserMenuPayload(action="cancel").pack())],
        ]
    ).pack()


def build_wifi_scope_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Проблема у одного гостя",
                    payload=UserMenuPayload(action="wifi_scope_one").pack(),
                )
            ],
            [
                CallbackButton(
                    text="Проблема у всех гостей",
                    payload=UserMenuPayload(action="wifi_scope_all").pack(),
                )
            ],
            [CallbackButton(text="Отмена", payload=UserMenuPayload(action="menu").pack())],
        ]
    ).pack()


def build_wifi_device_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Смартфон / планшет",
                    payload=UserMenuPayload(action="wifi_device_mobile").pack(),
                )
            ],
            [
                CallbackButton(
                    text="Ноутбук",
                    payload=UserMenuPayload(action="wifi_device_laptop").pack(),
                )
            ],
            [CallbackButton(text="Отмена", payload=UserMenuPayload(action="menu").pack())],
        ]
    ).pack()


def build_wifi_auth_keyboard():
    return ButtonsPayload(
        buttons=[
            [CallbackButton(text="Да", payload=UserMenuPayload(action="wifi_auth_yes").pack())],
            [CallbackButton(text="Нет", payload=UserMenuPayload(action="wifi_auth_no").pack())],
            [CallbackButton(text="Отмена", payload=UserMenuPayload(action="menu").pack())],
        ]
    ).pack()


def build_wifi_resolution_keyboard():
    return ButtonsPayload(
        buttons=[
            [CallbackButton(text="Проблема решена", payload=UserMenuPayload(action="wifi_resolved").pack())],
            [
                CallbackButton(
                    text="Проблема не решена",
                    payload=UserMenuPayload(action="wifi_unresolved").pack(),
                )
            ],
        ]
    ).pack()


def build_wifi_escalation_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Мои обращения",
                    payload=UserMenuPayload(action="my").pack(),
                )
            ],
            [
                CallbackButton(
                    text="В главное меню",
                    payload=UserMenuPayload(action="menu").pack(),
                )
            ],
            [
                CallbackButton(
                    text="Назад",
                    payload=UserMenuPayload(action="wifi").pack(),
                )
            ],
        ]
    ).pack()


def build_tv_escalation_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Мои обращения",
                    payload=UserMenuPayload(action="my").pack(),
                )
            ],
            [
                CallbackButton(
                    text="В главное меню",
                    payload=UserMenuPayload(action="menu").pack(),
                )
            ],
            [
                CallbackButton(
                    text="Назад",
                    payload=UserMenuPayload(action="tv_guest").pack(),
                )
            ],
        ]
    ).pack()


def build_admin_menu_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Заявки на доступ",
                    payload=UserMenuPayload(action="admin_pending").pack(),
                )
            ],
            [
                CallbackButton(
                    text="Список Пользователей",
                    payload=UserMenuPayload(action="admin_users").pack(),
                )
            ],
            [CallbackButton(text="Главное меню", payload=UserMenuPayload(action="menu").pack())],
        ]
    ).pack()


def build_admin_pending_keyboard(user_ids: list[int]):
    """Собирает список pending-заявок на доступ для администратора."""

    rows: list[list[CallbackButton]] = []
    for user_id in user_ids:
        rows.append(
            [
                CallbackButton(
                    text="Одобрить",
                    payload=UserMenuPayload(action="admin_approve", value=str(user_id)).pack(),
                ),
                CallbackButton(
                    text="Отказать",
                    payload=UserMenuPayload(action="admin_reject", value=str(user_id)).pack(),
                ),
            ]
        )

    rows.append(
        [CallbackButton(text="Обновить список", payload=UserMenuPayload(action="admin_pending").pack())]
    )
    rows.append([CallbackButton(text="Назад", payload=UserMenuPayload(action="admin_help").pack())])
    return ButtonsPayload(buttons=rows).pack()


def build_admin_request_keyboard(user_id: int):
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Одобрить",
                    payload=UserMenuPayload(action="admin_approve", value=str(user_id)).pack(),
                ),
                CallbackButton(
                    text="Отказать",
                    payload=UserMenuPayload(action="admin_reject", value=str(user_id)).pack(),
                ),
            ]
        ]
    ).pack()


def build_admin_role_select_keyboard(user_id: int):
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Администратор",
                    payload=UserMenuPayload(action="admin_role_admin", value=str(user_id)).pack(),
                )
            ],
            [
                CallbackButton(
                    text="IT специалист",
                    payload=UserMenuPayload(action="admin_role_it", value=str(user_id)).pack(),
                )
            ],
            [
                CallbackButton(
                    text="Пользователь",
                    payload=UserMenuPayload(action="admin_role_user", value=str(user_id)).pack(),
                )
            ],
            [
                CallbackButton(
                    text="Назад",
                    payload=UserMenuPayload(action="admin_pending_one", value=str(user_id)).pack(),
                )
            ],
        ]
    ).pack()


def build_admin_users_keyboard(user_entries: list[tuple[int, str]]):
    """Собирает клавиатуру списка зарегистрированных пользователей."""

    rows: list[list[CallbackButton]] = []
    for user_id, user_name in user_entries:
        label = (user_name or f"ID {user_id}").strip()
        if len(label) > 24:
            label = f"{label[:21]}..."
        rows.append(
            [
                CallbackButton(
                    text=f"Открыть: {label}",
                    payload=UserMenuPayload(action="admin_user_open", value=str(user_id)).pack(),
                ),
            ]
        )

    rows.append(
        [CallbackButton(text="Обновить список", payload=UserMenuPayload(action="admin_users").pack())]
    )
    rows.append([CallbackButton(text="Назад", payload=UserMenuPayload(action="admin_help").pack())])
    return ButtonsPayload(buttons=rows).pack()


def build_admin_user_actions_keyboard(user_id: int):
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Назначить отель",
                    payload=UserMenuPayload(action="admin_user_hotel", value=str(user_id)).pack(),
                )
            ],
            [
                CallbackButton(
                    text="Бан",
                    payload=UserMenuPayload(action="admin_ban", value=str(user_id)).pack(),
                ),
                CallbackButton(
                    text="Удалить",
                    payload=UserMenuPayload(action="admin_delete_user", value=str(user_id)).pack(),
                ),
            ],
            [
                CallbackButton(
                    text="К списку",
                    payload=UserMenuPayload(action="admin_users").pack(),
                )
            ],
            [
                CallbackButton(
                    text="Назад",
                    payload=UserMenuPayload(action="admin_help").pack(),
                )
            ],
        ]
    ).pack()


def build_registration_keyboard():
    return ButtonsPayload(
        buttons=[
            [RequestContactButton(text="Зарегистрироваться (поделиться контактом)")],
        ]
    ).pack()


def build_ticket_actions_keyboard(ticket_id: str):
    """Собирает кнопки действий специалиста по заявке."""

    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Взять в работу",
                    payload=SpecialistTicketPayload(action="take", ticket_id=ticket_id).pack(),
                )
            ],
            [
                CallbackButton(
                    text="Освободить",
                    payload=SpecialistTicketPayload(action="release", ticket_id=ticket_id).pack(),
                ),
                CallbackButton(
                    text="Закрыть",
                    payload=SpecialistTicketPayload(action="close", ticket_id=ticket_id).pack(),
                ),
            ],
            [
                CallbackButton(
                    text="Не закрытые заявки",
                    payload=SpecialistTicketPayload(action="open_list", ticket_id=ticket_id).pack(),
                )
            ],
        ]
    ).pack()


def build_open_tickets_keyboard(tickets, *, max_buttons: int = 20):
    """Собирает компактную клавиатуру открытых заявок."""

    rows: list[list[CallbackButton]] = []
    row: list[CallbackButton] = []

    for ticket in tickets[:max_buttons]:
        row.append(
            CallbackButton(
                text=ticket.ticket_id,
                payload=SpecialistTicketPayload(
                    action="open_card",
                    ticket_id=ticket.ticket_id,
                ).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append(
        [
            CallbackButton(
                text="Обновить список",
                payload=SpecialistTicketPayload(action="open_list", ticket_id="-").pack(),
            )
        ]
    )
    return ButtonsPayload(buttons=rows).pack()


def build_admin_hotel_select_keyboard(user_id: int, hotels: tuple[tuple[str, str], ...]):
    rows: list[list[CallbackButton]] = []
    for hotel_code, hotel_label in hotels:
        rows.append(
            [
                CallbackButton(
                    text=hotel_label,
                    payload=UserMenuPayload(
                        action="admin_hotel_set",
                        value=f"{user_id}:{hotel_code}",
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            CallbackButton(
                text="Снять привязку",
                payload=UserMenuPayload(action="admin_hotel_set", value=f"{user_id}:none").pack(),
            )
        ]
    )
    rows.append(
        [
            CallbackButton(
                text="Назад",
                payload=UserMenuPayload(action="admin_user_open", value=str(user_id)).pack(),
            )
        ]
    )
    return ButtonsPayload(buttons=rows).pack()
