from maxapi.types import ButtonsPayload, CallbackButton

from app.helpdesk.payloads import SpecialistTicketPayload, UserMenuPayload


def build_main_menu_keyboard():
    return ButtonsPayload(
        buttons=[
            [CallbackButton(text="Создать обращение", payload=UserMenuPayload(action="create").pack())],
            [CallbackButton(text="Мои обращения", payload=UserMenuPayload(action="my").pack())],
            [CallbackButton(text="Wi-Fi и сеть", payload=UserMenuPayload(action="wifi").pack())],
            [CallbackButton(text="Помощь", payload=UserMenuPayload(action="help").pack())],
        ]
    ).pack()


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

