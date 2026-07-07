"""Обработка текстового ввода для сетевых инструментов."""

import logging

from maxapi.enums.parse_mode import ParseMode
from maxapi.types import MessageCreated

from app.admin.runtime import get_user_access_registry
from app.admin.services.access_service import can_use_network_tools
from app.network.keyboards.network_keyboards import (
    build_network_main_menu_keyboard,
    build_network_menu_keyboard,
)
from app.network.runtime import (
    get_netarium_guest_service,
    get_network_session_service,
    get_network_tools_service,
    get_wifi_voucher_service,
)
from app.network.netarium.guest_texts import render_guest_search_result
from app.network.texts import network_texts
from app.network.wifi.voucher_texts import render_voucher_search_result
from config.config import get_config

logger = logging.getLogger(__name__)


def register(dp) -> None:
    """Регистрирует ввод целей для сетевых инструментов."""

    cfg = get_config()
    network_tools = get_network_tools_service()
    network_session = get_network_session_service()
    wifi_vouchers = get_wifi_voucher_service()
    netarium_guests = get_netarium_guest_service()
    access_registry = get_user_access_registry()

    def _resolve_role_sets():
        """Объединяет роли админов и IT из .env и реестра."""

        admin_ids = set(cfg.bot.admin_ids) | set(access_registry.get_ids_by_role("admin"))
        specialist_ids = set(cfg.bot.it_specialist_ids) | set(
            access_registry.get_ids_by_role("IT specialist")
        )
        return tuple(admin_ids), tuple(specialist_ids)

    @dp.message_created()
    async def handle_network_target_input(event: MessageCreated):
        text = (event.message.body.text or "").strip()
        if not text:
            return

        actor_id = int(event.message.sender.user_id)
        admin_ids, specialist_ids = _resolve_role_sets()
        is_allowed = can_use_network_tools(
            user_id=actor_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        )
        if not is_allowed:
            return

        if text.startswith("/net "):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                await event.message.answer(
                    "Формат: /net <tool> <target>\n"
                    "tools: ping, dns, host_check, traceroute, nslookup, whois"
                )
                return

            tool = parts[1].strip().lower()
            target = parts[2].strip()
            logger.info("/net command: user_id=%s tool=%s target=%s", actor_id, tool, target)
            result = await network_tools.run_tool(
                tool,
                target,
                actor_user_id=actor_id,
                actor_name=getattr(event.message.sender, "name", None),
            )
            await event.message.answer(
                text=network_texts.render_result(result.title, result.ok, result.details),
                attachments=[build_network_menu_keyboard()],
            )
            return

        if event.message.recipient.chat_type != "dialog":
            return

        if text.startswith("/"):
            return

        session = network_session.get(actor_id)
        if session.step != "awaiting_target" or not session.pending_tool:
            return

        if session.pending_tool == "wifi_voucher":
            logger.info("WiFi voucher room received: user_id=%s room=%s", actor_id, text)
            # Проверка комнаты в Netarium защищает от долгого обхода WiFi.link
            # при явной ошибке в номере.
            guest_result = await netarium_guests.find_by_room(
                text,
                actor_user_id=actor_id,
                actor_name=actor_name,
                chat_type=event.message.recipient.chat_type,
            )
            if not guest_result.ok:
                await event.message.answer(
                    text=render_guest_search_result(guest_result),
                    attachments=[build_network_main_menu_keyboard()],
                    format=ParseMode.HTML,
                )
                return
            if not guest_result.room_exists:
                await event.message.answer(
                    text="Такого номера не существует",
                    attachments=[build_network_main_menu_keyboard()],
                )
                return

            # Состояние не сбрасываем: администратор может вводить комнаты подряд.
            result = await wifi_vouchers.find_first_by_room(
                text,
                actor_user_id=actor_id,
                actor_name=actor_name,
                chat_type=event.message.recipient.chat_type,
                room_exists_in_netarium=guest_result.room_exists,
                guest_found_in_netarium=guest_result.stay is not None,
            )
            await event.message.answer(
                text=render_voucher_search_result(result),
                format=ParseMode.HTML,
            )
            await event.message.answer(
                text=render_guest_search_result(guest_result),
                attachments=[build_network_main_menu_keyboard()],
                format=ParseMode.HTML,
            )
            return

        logger.info(
            "Network target received: user_id=%s tool=%s target=%s",
            actor_id,
            session.pending_tool,
            text,
        )
        result = await network_tools.run_tool(
            session.pending_tool,
            text,
            actor_user_id=actor_id,
            actor_name=getattr(event.message.sender, "name", None),
        )
        network_session.mark_processed(actor_id)
        await event.message.answer(
            text=network_texts.render_result(result.title, result.ok, result.details),
            attachments=[build_network_menu_keyboard()],
        )
