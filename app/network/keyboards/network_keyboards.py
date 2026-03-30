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
                CallbackButton(
                    text="DNS lookup",
                    payload=NetworkMenuPayload(action="tool", value="dns").pack(),
                ),
            ],
            [
                CallbackButton(
                    text="Host check",
                    payload=NetworkMenuPayload(action="tool", value="host_check").pack(),
                ),
                CallbackButton(
                    text="Traceroute",
                    payload=NetworkMenuPayload(action="tool", value="traceroute").pack(),
                ),
            ],
            [
                CallbackButton(
                    text="NSLookup",
                    payload=NetworkMenuPayload(action="tool", value="nslookup").pack(),
                ),
                CallbackButton(
                    text="Whois",
                    payload=NetworkMenuPayload(action="tool", value="whois").pack(),
                ),
            ],
            [
                CallbackButton(
                    text="Wi-Fi шаблоны",
                    payload=NetworkMenuPayload(action="wifi").pack(),
                ),
                CallbackButton(
                    text="Device шаблоны",
                    payload=NetworkMenuPayload(action="device_menu").pack(),
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

