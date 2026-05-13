"""Фабрики inline-клавиатур сетевых инструментов."""

from maxapi.types import ButtonsPayload, CallbackButton

from app.network.payloads import NetworkMenuPayload


def build_network_menu_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Ping",
                    payload=NetworkMenuPayload(action="tool", value="ping").pack(),
                ),
            ],
            [
                CallbackButton(
                    text="WiFi",
                    payload=NetworkMenuPayload(action="wifi").pack(),
                ),
            ],
            [
                CallbackButton(
                    text="Главное меню",
                    payload=NetworkMenuPayload(action="main_menu").pack(),
                ),
            ],
        ]
    ).pack()


def build_network_main_menu_keyboard():
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text="Главное меню",
                    payload=NetworkMenuPayload(action="main_menu").pack(),
                ),
            ],
        ]
    ).pack()


def build_device_type_keyboard(device_types: tuple[str, ...]):
    rows: list[list[CallbackButton]] = []
    for device_type in device_types:
        rows.append(
            [
                CallbackButton(
                    text=device_type,
                    payload=NetworkMenuPayload(action="device", value=device_type).pack(),
                )
            ]
        )
    rows.append(
        [
            CallbackButton(
                text="Назад",
                payload=NetworkMenuPayload(action="menu").pack(),
            )
        ]
    )
    return ButtonsPayload(buttons=rows).pack()
