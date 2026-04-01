import logging

from maxapi.types import MessageCallback

from app.admin.services.access_service import can_use_network_tools
from app.helpdesk.keyboards.helpdesk_keyboards import build_main_menu_keyboard
from app.network.keyboards.network_keyboards import (
    build_device_type_keyboard,
    build_network_menu_keyboard,
)
from app.network.payloads import NetworkMenuPayload
from app.network.runtime import get_network_session_service, get_network_tools_service
from app.network.texts import network_texts
from config.config import get_config

logger = logging.getLogger(__name__)


def register(dp) -> None:
    cfg = get_config()
    network_tools = get_network_tools_service()
    network_session = get_network_session_service()

    @dp.message_callback(NetworkMenuPayload.filter())
    async def handle_network_menu_callback(
        event: MessageCallback, payload: NetworkMenuPayload
    ):
        if event.message.recipient.chat_type != "dialog":
            await event.answer(notification="Используйте сетевое меню в личном диалоге с ботом.")
            return

        actor_id = int(event.callback.user.user_id)
        is_allowed = can_use_network_tools(
            user_id=actor_id,
            admin_ids=cfg.bot.admin_ids,
            specialist_ids=cfg.bot.it_specialist_ids,
        )
        if not is_allowed:
            logger.info("Network menu denied for user_id=%s", actor_id)
            await event.answer(notification=network_texts.NO_ACCESS_TEXT)
            return

        action = payload.action
        if action in {"menu", "open"}:
            network_session.reset(actor_id)
            await event.message.answer(
                text=network_texts.NETWORK_MENU_TEXT,
                attachments=[build_network_menu_keyboard()],
            )
            await event.answer(notification="Открыто сетевое меню")
            return

        if action == "main_menu":
            network_session.reset(actor_id)
            await event.message.answer(
                text="Возврат в главное меню.",
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Главное меню")
            return

        if action == "wifi":
            result = network_tools.wifi_template()
            await event.message.answer(
                text=network_texts.render_result(result.title, result.ok, result.details),
                attachments=[build_network_menu_keyboard()],
            )
            await event.answer(notification="Шаблон Wi-Fi")
            return

        if action == "device_menu":
            await event.message.answer(
                text="Выберите тип устройства:",
                attachments=[
                    build_device_type_keyboard(
                        cfg.network_tools.policy.allowed_device_types
                    )
                ],
            )
            await event.answer(notification="Меню устройств")
            return

        if action == "device":
            result = network_tools.device_template(payload.value)
            await event.message.answer(
                text=network_texts.render_result(result.title, result.ok, result.details),
                attachments=[build_network_menu_keyboard()],
            )
            await event.answer(notification="Шаблон устройства")
            return

        if action == "tool":
            tool = payload.value
            prompt = network_texts.PROMPT_BY_TOOL.get(tool)
            if not prompt:
                await event.answer(notification=network_texts.UNKNOWN_TOOL_TEXT)
                return

            network_session.expect_target(actor_id, tool)
            logger.info("Network tool selected: user_id=%s tool=%s", actor_id, tool)
            await event.message.answer(
                text=prompt,
                attachments=[build_network_menu_keyboard()],
            )
            await event.answer(notification="Ожидаю адрес")
            return

        await event.answer(notification="Неизвестное действие")
