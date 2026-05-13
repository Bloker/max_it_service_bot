"""Callback-обработчики раздела сетевых инструментов."""

import logging

from maxapi.types import MessageCallback

from app.admin.runtime import get_user_access_registry
from app.admin.services.access_service import (
    can_use_network_tools,
    can_view_service_functions,
    is_admin,
)
from app.helpdesk.keyboards.helpdesk_keyboards import build_main_menu_keyboard
from app.network.keyboards.network_keyboards import (
    build_device_type_keyboard,
    build_network_main_menu_keyboard,
    build_network_menu_keyboard,
)
from app.network.payloads import NetworkMenuPayload
from app.network.runtime import get_network_session_service, get_network_tools_service
from app.network.texts import network_texts
from config.config import get_config

logger = logging.getLogger(__name__)


def register(dp) -> None:
    """Регистрирует callback-обработчик сетевого меню."""

    cfg = get_config()
    network_tools = get_network_tools_service()
    network_session = get_network_session_service()
    access_registry = get_user_access_registry()

    def _resolve_role_sets():
        """Объединяет роли админов и IT из .env и реестра."""

        admin_ids = set(cfg.bot.admin_ids) | set(access_registry.get_ids_by_role("admin"))
        specialist_ids = set(cfg.bot.it_specialist_ids) | set(
            access_registry.get_ids_by_role("IT specialist")
        )
        return tuple(admin_ids), tuple(specialist_ids)

    def _build_main_menu_for_user(user_id: int):
        """Собирает главное меню после выхода из сетевых инструментов."""

        admin_ids, specialist_ids = _resolve_role_sets()
        can_view_service = can_view_service_functions(
            user_id=user_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        )
        hotel_code = access_registry.get_user_hotel(user_id)
        hotel_features = set(access_registry.get_hotel_features(hotel_code))
        is_service_actor = can_view_service
        return build_main_menu_keyboard(
            can_create_ticket=True,
            can_view_my_tickets=True,
            can_view_help=not is_service_actor,
            can_view_about=not is_service_actor,
            can_use_network_tools=can_use_network_tools(
                user_id=user_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ),
            can_view_service_functions=can_view_service,
            is_admin=is_admin(user_id, admin_ids),
            can_use_wifi_help=not is_service_actor and "wifi_guest_issue" in hotel_features,
            can_use_tv_help=not is_service_actor and "tv_guest_issue" in hotel_features,
        )

    @dp.message_callback(NetworkMenuPayload.filter())
    async def handle_network_menu_callback(
        event: MessageCallback, payload: NetworkMenuPayload
    ):
        if event.message.recipient.chat_type != "dialog":
            await event.answer(notification="Используйте сетевое меню в личном диалоге с ботом.")
            return

        actor_id = int(event.callback.user.user_id)
        admin_ids, specialist_ids = _resolve_role_sets()
        is_allowed = can_use_network_tools(
            user_id=actor_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
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
                attachments=[_build_main_menu_for_user(actor_id)],
            )
            await event.answer(notification="Главное меню")
            return

        if action in {"wifi", "wifi_voucher"}:
            # WiFi работает как режим ввода: после каждого номера можно сразу
            # отправлять следующий, пока пользователь не вернется в главное меню.
            network_session.expect_target(actor_id, "wifi_voucher")
            await event.message.answer(
                text=network_texts.WIFI_ROOM_PROMPT_TEXT,
                attachments=[build_network_main_menu_keyboard()],
            )
            await event.answer(notification="Ожидаю номер комнаты")
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
