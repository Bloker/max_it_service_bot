from maxapi.types import ButtonsPayload, CallbackButton, RequestContactButton

from app.helpdesk.payloads import SpecialistTicketPayload, UserMenuPayload


def build_main_menu_keyboard(
    *,
    can_use_network_tools: bool = False,
    can_view_service_functions: bool = False,
    is_admin: bool = False,
    can_use_wifi_help: bool = True,
):
    buttons = [
        [CallbackButton(text="Создать обращение", payload=UserMenuPayload(action="create").pack())],
        [CallbackButton(text="Мои обращения", payload=UserMenuPayload(action="my").pack())],
        [CallbackButton(text="Помощь", payload=UserMenuPayload(action="help").pack())],
    ]

    if can_use_wifi_help:
        buttons.insert(
            2,
            [CallbackButton(text="Проблема Wi-Fi у гостя", payload=UserMenuPayload(action="wifi").pack())],
        )

    if can_use_network_tools:
        buttons.append(
            [
                CallbackButton(
                    text="Сетевые инструменты",
                    payload=UserMenuPayload(action="network").pack(),
                )
            ]
        )

    if can_view_service_functions:
        buttons.append(
            [
                CallbackButton(
                    text="Сервисные команды",
                    payload=UserMenuPayload(action="service_help").pack(),
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
    rows = [
        [CallbackButton(text=category, payload=UserMenuPayload(action="cat", value=category).pack())]
        for category in categories
    ]
    rows.append([CallbackButton(text="Назад", payload=UserMenuPayload(action="menu").pack())])
    return ButtonsPayload(buttons=rows).pack()


def build_confirm_keyboard():
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
                    text="Запросить уточнение",
                    payload=SpecialistTicketPayload(action="clarify", ticket_id=ticket_id).pack(),
                )
            ],
        ]
    ).pack()
