class TicketLinkService:
    """Ephemeral runtime mapping between ticket ids and group chat message ids."""

    def __init__(self) -> None:
        self._ticket_to_group_mid: dict[str, str] = {}
        self._group_mid_to_ticket: dict[str, str] = {}

    def bind_group_message(self, ticket_id: str, group_message_id: str) -> None:
        self._ticket_to_group_mid[ticket_id] = group_message_id
        self._group_mid_to_ticket[group_message_id] = ticket_id

    def get_group_message_id(self, ticket_id: str) -> str | None:
        return self._ticket_to_group_mid.get(ticket_id)

    def get_ticket_id_by_group_message(self, group_message_id: str) -> str | None:
        return self._group_mid_to_ticket.get(group_message_id)

