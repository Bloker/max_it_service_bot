class TicketLinkService:
    """Ephemeral runtime mapping between ticket ids and group chat message ids."""

    def __init__(self) -> None:
        self._ticket_to_group_mid: dict[str, str] = {}
        self._group_mid_to_ticket: dict[str, str] = {}
        self._user_mid_to_ticket: dict[str, str] = {}

    def bind_group_message(
        self,
        ticket_id: str,
        group_message_id: str,
        *,
        primary: bool = False,
    ) -> None:
        normalized_group_mid = str(group_message_id)
        if primary or ticket_id not in self._ticket_to_group_mid:
            self._ticket_to_group_mid[ticket_id] = normalized_group_mid
        self._group_mid_to_ticket[normalized_group_mid] = ticket_id

    def get_group_message_id(self, ticket_id: str) -> str | None:
        return self._ticket_to_group_mid.get(ticket_id)

    def get_ticket_id_by_group_message(self, group_message_id: str) -> str | None:
        return self._group_mid_to_ticket.get(str(group_message_id))

    def bind_user_message(self, ticket_id: str, user_message_id: str) -> None:
        self._user_mid_to_ticket[str(user_message_id)] = ticket_id

    def get_ticket_id_by_user_message(self, user_message_id: str) -> str | None:
        return self._user_mid_to_ticket.get(str(user_message_id))

