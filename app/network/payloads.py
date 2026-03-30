from maxapi.filters.callback_payload import CallbackPayload


class NetworkMenuPayload(CallbackPayload, prefix="net"):
    action: str
    value: str = ""

