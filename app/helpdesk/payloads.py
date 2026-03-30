from maxapi.filters.callback_payload import CallbackPayload


class UserMenuPayload(CallbackPayload, prefix="usr"):
    action: str
    value: str = ""


class SpecialistTicketPayload(CallbackPayload, prefix="spc"):
    action: str
    ticket_id: str

