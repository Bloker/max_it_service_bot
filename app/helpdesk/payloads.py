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


class ClarificationCancelPayload(CallbackPayload, prefix="clc"):
    """Payload отмены ожидающего вопроса уточнения."""

    ticket_id: str


class CloseReplyCancelPayload(CallbackPayload, prefix="crc"):
    """Payload отмены закрытия заявки с ответом."""

    ticket_id: str


class InternalCommentCancelPayload(CallbackPayload, prefix="tic"):
    """Payload отмены ввода внутреннего комментария специалиста."""

    ticket_id: str
