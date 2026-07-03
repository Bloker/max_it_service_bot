import unittest

from app.helpdesk.payloads import (
    ClarificationCancelPayload,
    SpecialistTicketPayload,
    UserMenuPayload,
)
from app.network.payloads import NetworkMenuPayload


class CallbackPayloadTests(unittest.TestCase):
    def test_user_menu_payload_round_trip(self) -> None:
        payload = UserMenuPayload(action="cat", value="VPN")

        packed = payload.pack()
        unpacked = UserMenuPayload.unpack(packed)

        self.assertEqual(packed, "usr|cat|VPN")
        self.assertEqual(unpacked.action, "cat")
        self.assertEqual(unpacked.value, "VPN")

    def test_specialist_ticket_payload_round_trip(self) -> None:
        payload = SpecialistTicketPayload(action="take", ticket_id="T-00001")

        packed = payload.pack()
        unpacked = SpecialistTicketPayload.unpack(packed)

        self.assertEqual(packed, "spc|take|T-00001")
        self.assertEqual(unpacked.action, "take")
        self.assertEqual(unpacked.ticket_id, "T-00001")

    def test_clarification_cancel_payload_round_trip(self) -> None:
        payload = ClarificationCancelPayload(ticket_id="T-00001")

        packed = payload.pack()
        unpacked = ClarificationCancelPayload.unpack(packed)

        self.assertEqual(packed, "clc|T-00001")
        self.assertEqual(unpacked.ticket_id, "T-00001")

    def test_network_menu_payload_round_trip(self) -> None:
        payload = NetworkMenuPayload(action="tool", value="ping")

        packed = payload.pack()
        unpacked = NetworkMenuPayload.unpack(packed)

        self.assertEqual(packed, "net|tool|ping")
        self.assertEqual(unpacked.action, "tool")
        self.assertEqual(unpacked.value, "ping")


if __name__ == "__main__":
    unittest.main()
