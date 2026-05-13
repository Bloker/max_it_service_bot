"""Callback payload-классы пользовательского и IT-меню."""

from maxapi.filters.callback_payload import CallbackPayload


class UserMenuPayload(CallbackPayload, prefix="usr"):
    """Payload inline-кнопок пользовательского меню."""

    action: str
    value: str = ""


class SpecialistTicketPayload(CallbackPayload, prefix="spc"):
    """Payload действий специалиста над заявкой."""

    action: str
    ticket_id: str
