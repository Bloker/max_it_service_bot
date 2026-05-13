"""Callback payload-класс сетевого меню."""

from maxapi.filters.callback_payload import CallbackPayload


class NetworkMenuPayload(CallbackPayload, prefix="net"):
    """Payload inline-кнопок сетевого меню."""

    action: str
    value: str = ""
