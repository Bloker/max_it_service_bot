"""Форматирование карточки WiFi-ваучера."""

from html import escape

from app.network.wifi.models import WifiVoucherSearchResult


def render_voucher_search_result(result: WifiVoucherSearchResult) -> str:
    """Форматирует результат поиска WiFi-ваучера для MAX-сообщения."""

    room = escape(result.room or "-")
    if not result.ok:
        return f"<b>WiFi ваучер: комната {room}</b>\n{escape(result.error)}"

    if not result.vouchers:
        return (
            f"<b>WiFi ваучер: комната {room}</b>\n"
            "Ваучеры для этой комнаты не найдены в проверенном списке."
        )

    lines = [f"<b>WiFi ваучер: комната {room}</b>"]
    for index, voucher in enumerate(result.vouchers, start=1):
        if len(result.vouchers) > 1:
            lines.extend(["", f"<b>Ваучер {index}</b>"])
        else:
            lines.append("")

        lines.extend(
            [
                f"Логин: <code>{escape(voucher.login)}</code>",
                f"Гость: {escape(voucher.guest or '-')}",
                f"Скорость: {escape(voucher.speed_mbps)} Мбит/сек",
                f"Времени прошло: {escape(voucher.elapsed_hours)} ч",
                f"Времени осталось: {escape(voucher.remaining_hours)} ч",
                f"Скачано: {escape(voucher.downloaded_mb)} МБ",
                f"Годность: <b>{escape(voucher.validity)}</b>",
                f"Создан: {escape(voucher.created_raw)}",
            ]
        )

    return "\n".join(lines)
