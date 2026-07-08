from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.room_ticket_history import RoomTicketHistoryItem
from app.helpdesk.texts.room_history_texts import render_room_history


class RoomHistoryTextsTests(unittest.TestCase):
    def test_render_room_history_outputs_header_location_and_items(self) -> None:
        context = RoomTicketContext(
            ticket_key="T-00088",
            hotel_id=1,
            location_id=12,
            room_number_snapshot="112",
            location_display_snapshot="Джамайка · 1 корпус · номер 112",
        )
        items = [
            RoomTicketHistoryItem(
                ticket_key="T-00072",
                hotel_id=1,
                location_id=12,
                category_snapshot="Интернет",
                status="закрыто",
                created_at=datetime(2026, 7, 7, 11, 12, tzinfo=ZoneInfo("UTC")),
            ),
            RoomTicketHistoryItem(
                ticket_key="T-00061",
                hotel_id=1,
                location_id=12,
                category_snapshot="Замок",
                status="в работе",
                created_at=datetime(2026, 7, 4, 6, 5, tzinfo=ZoneInfo("UTC")),
            ),
        ]

        text = render_room_history(room_context=context, items=items)

        self.assertIn("<b>История номера</b>", text)
        self.assertIn("Объект:\nНомер 112", text)
        self.assertIn("Последние 2 заявки:", text)
        self.assertIn("<code>T-00072</code> · Интернет · закрыто · 07.07 14:12", text)
        self.assertIn("<code>T-00061</code> · Замок · в работе · 04.07 09:05", text)

    def test_render_room_history_for_cottage_and_empty_list(self) -> None:
        context = RoomTicketContext(
            ticket_key="T-00091",
            hotel_id=1,
            location_id=15,
            room_number_snapshot="15",
            location_display_snapshot="Джамайка · Домик 15",
        )

        text = render_room_history(room_context=context, items=[])

        self.assertIn("Объект:\nДомик 15", text)
        self.assertIn("Других заявок по этому номеру не найдено.", text)

    def test_render_room_history_escapes_values_and_uses_fallbacks(self) -> None:
        context = RoomTicketContext(
            ticket_key="T-00092",
            hotel_id=1,
            location_id=21,
            room_number_snapshot="21<script>",
            location_display_snapshot="Джамайка · 1 корпус · номер 21<script>",
        )
        items = [
            RoomTicketHistoryItem(
                ticket_key="T-00100",
                hotel_id=1,
                location_id=21,
                category_snapshot="<b>bad</b>",
                status=None,
                created_at=datetime(2026, 7, 8, 8, 0, tzinfo=ZoneInfo("UTC")),
            ),
            RoomTicketHistoryItem(
                ticket_key="T-00101",
                hotel_id=1,
                location_id=21,
                category_snapshot=None,
                status="в работе",
                created_at=datetime(2026, 7, 8, 9, 0, tzinfo=ZoneInfo("UTC")),
            ),
        ]

        text = render_room_history(room_context=context, items=items)

        self.assertIn("Номер 21&lt;script&gt;", text)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt; · неизвестно", text)
        self.assertIn("Без категории · в работе", text)
        self.assertNotIn("+7", text)


if __name__ == "__main__":
    unittest.main()
