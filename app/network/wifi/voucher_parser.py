"""Парсинг HTML-таблицы ваучеров WiFi.link."""

from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
from re import sub

from app.network.wifi.models import WifiVoucher


class _VoucherTableParser(HTMLParser):
    """Минимальный HTML-парсер таблицы ваучеров WiFi.link."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_tr = False
        self._in_td = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._in_tr = True
            self._current_row = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            text = _normalize_cell_text("".join(self._current_cell))
            self._current_row.append(text)
            self._in_td = False
            self._current_cell = []
        elif tag == "tr" and self._in_tr:
            if self._current_row:
                self.rows.append(self._current_row)
            self._in_tr = False
            self._current_row = []


def _normalize_cell_text(raw: str) -> str:
    return sub(r"\s+", " ", unescape(raw)).strip()


def _parse_created_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%d.%m.%y").date()
    except ValueError:
        return None


def _extract_room_and_guest(login: str) -> tuple[str, str]:
    """Извлекает комнату и фамилию из логина вида `...:3219:moiseenko`."""

    parts = login.split(":")
    if len(parts) < 3:
        return "", ""
    return parts[-2].strip(), parts[-1].strip()


def parse_wifi_vouchers(html: str) -> list[WifiVoucher]:
    """Преобразует HTML-таблицу WiFi.link в список безопасных моделей."""

    parser = _VoucherTableParser()
    parser.feed(html)

    vouchers: list[WifiVoucher] = []
    for row in parser.rows:
        if len(row) < 10:
            continue

        # Индексы соответствуют текущим колонкам таблицы WiFi.link.
        # Пароль и остаток трафика намеренно не читаем в модель.
        login = row[1]
        room, guest = _extract_room_and_guest(login)
        created_raw = row[9]
        created_date = _parse_created_date(created_raw)
        if not login or not room or created_date is None:
            continue

        vouchers.append(
            WifiVoucher(
                login=login,
                room=room,
                guest=guest,
                speed_mbps=row[3],
                elapsed_hours=row[4],
                remaining_hours=row[5],
                downloaded_mb=row[6],
                validity=row[8],
                created_date=created_date,
                created_raw=created_raw,
            )
        )

    return vouchers
