"""Callback-обработчики пользовательского, админского и HelpDesk-меню."""

import logging

from maxapi.enums.message_link_type import MessageLinkType
from maxapi.enums.parse_mode import ParseMode
from maxapi.types import MessageCallback
from maxapi.types.message import NewMessageLink

from app.admin.runtime import get_user_access_registry
from app.admin.services.access_service import (
    can_change_ticket_status,
    can_take_ticket,
    can_use_network_tools,
    can_view_service_functions,
    can_view_user_menu,
    is_admin,
)
from app.bot.notifications import notify_user_ticket_closed
from app.bot.services.max_message_service import MaxMessageService
from app.common.user_helpers import get_full_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_admin_hotel_select_keyboard,
    build_admin_menu_keyboard,
    build_admin_request_keyboard,
    build_admin_role_select_keyboard,
    build_admin_user_actions_keyboard,
    build_admin_users_keyboard,
    build_clarification_cancel_keyboard,
    build_close_reply_cancel_keyboard,
    build_categories_keyboard,
    build_jamaica_cancel_keyboard,
    build_jamaica_main_menu_keyboard,
    build_main_menu_keyboard,
    build_open_tickets_keyboard,
    build_ticket_actions_keyboard,
    build_wifi_auth_keyboard,
    build_wifi_device_keyboard,
    build_wifi_escalation_keyboard,
    build_wifi_resolution_keyboard,
    build_wifi_scope_keyboard,
    build_tv_escalation_keyboard,
)
from app.helpdesk.models.ticket import TicketStatus
from app.helpdesk.payloads import (
    ClarificationCancelPayload,
    CloseReplyCancelPayload,
    SpecialistTicketPayload,
    UserMenuPayload,
)
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.runtime import (
    get_clarification_session_service,
    get_close_reply_session_service,
    get_room_history_service,
    get_room_ticket_context_service,
    get_ticket_clarification_service,
    get_ticket_link_service,
    get_ticket_service,
    get_user_reply_session_service,
    get_user_flow_service,
)
from app.helpdesk.services.menu_service import get_ticket_categories
from app.helpdesk.services.room_history_service import ROOM_HISTORY_LIMIT
from app.helpdesk.services.ticket_card_update_service import TicketCardUpdateService
from app.helpdesk.texts import room_history_texts, specialist_texts, user_texts
from app.network.keyboards.network_keyboards import build_network_menu_keyboard
from app.network.runtime import get_network_session_service
from app.observability.runtime import get_observability_service
from app.network.texts import network_texts
from config.config import get_config

logger = logging.getLogger(__name__)


def _build_user_ticket_list_text(lines: list[str]) -> str:
    """Собирает текст списка пользовательских заявок."""

    if not lines:
        return user_texts.NO_TICKETS_TEXT
    return f"{user_texts.MY_TICKETS_HEADER}\n" + "\n".join(lines)


def _extract_message_id(sent_message) -> str | None:
    """Достаёт MAX message_id из ответа отправки сообщения."""

    body = getattr(getattr(sent_message, "message", None), "body", None)
    mid = getattr(body, "mid", None)
    return str(mid) if mid else None


def _build_single_pending_text(item) -> str:
    """Форматирует одну заявку на доступ для администратора."""

    requested_at = str(item.requested_at or "")
    requested_at = requested_at.replace("T", " ")
    requested_at = requested_at.split("+", maxsplit=1)[0]
    requested_at = requested_at.split(".", maxsplit=1)[0]
    return (
        "Новая заявка на доступ:\n"
        f"ID: {item.user_id}\n"
        f"Имя: {item.user_name}\n"
        f"Телефон: {item.phone or '-'}\n"
        f"Дата: {requested_at}"
    )


def _find_pending_item(access_registry, user_id: int):
    """Ищет pending-заявку пользователя в реестре."""

    for item in access_registry.list_pending():
        if item.user_id == user_id:
            return item
    return None


def _build_users_text(users) -> str:
    """Форматирует список пользователей для админского меню."""

    if not users:
        return "Пользователей в базе нет."
    lines = ["Список пользователей:"]
    for idx, item in enumerate(users):
        lines.append(f"{item.user_id} | {item.user_name}")
        if idx < len(users) - 1:
            lines.append("")
    return "\n".join(lines)


def _build_open_tickets_text(items) -> str:
    return specialist_texts.render_open_tickets_list(items, title="Не закрытые заявки")


async def _send_ticket_card_from_list(
    event: MessageCallback,
    ticket,
    ticket_links,
    room_contexts=None,
) -> None:
    """Отправляет карточку заявки, по возможности reply к исходному сообщению."""

    group_message_id = ticket_links.get_group_message_id(ticket.ticket_id)
    room_context = room_contexts.get_context(ticket.ticket_id) if room_contexts else None
    if group_message_id:
        try:
            await event.message.answer(
                text=specialist_texts.render_group_ticket(
                    ticket,
                    room_context=room_context,
                ),
                attachments=[build_ticket_actions_keyboard(ticket, room_context=room_context)],
                link=NewMessageLink(type=MessageLinkType.REPLY, mid=group_message_id),
                format=ParseMode.HTML,
            )
            return
        except Exception:
            logger.exception(
                "Failed to send linked ticket card: ticket_id=%s group_message_id=%s",
                ticket.ticket_id,
                group_message_id,
            )

    await event.message.answer(
        text=specialist_texts.render_group_ticket(ticket, room_context=room_context),
        attachments=[build_ticket_actions_keyboard(ticket, room_context=room_context)],
        format=ParseMode.HTML,
    )


def _build_user_card_text(item, access_registry) -> str:
    """Форматирует карточку пользователя для администратора."""

    hotel_label = access_registry.get_hotel_label(item.hotel_code) or "-"
    lines = [
        "Пользователь:",
        f"ID: {item.user_id}",
        f"Имя: {item.user_name}",
        f"Телефон: {item.phone or '-'}",
        f"Отель: {hotel_label}",
        f"Роль: {item.role}",
        f"Статус: {item.status}",
    ]
    return "\n".join(lines)


def _find_user_item(access_registry, user_id: int):
    """Ищет зарегистрированного пользователя по MAX ID."""

    for item in access_registry.list_users():
        if item.user_id == user_id:
            return item
    return None


def _resolve_role_sets(cfg, access_registry):
    """Объединяет роли из .env и реестра пользователей."""

    admin_ids = set(cfg.bot.admin_ids) | set(access_registry.get_ids_by_role("admin"))
    specialist_ids = set(cfg.bot.it_specialist_ids) | set(
        access_registry.get_ids_by_role("IT specialist")
    )
    user_ids = set(cfg.bot.user_ids) | set(access_registry.get_ids_by_role("user"))
    return tuple(admin_ids), tuple(specialist_ids), tuple(user_ids)


def _build_menu_for_user(user_id: int, cfg, access_registry):
    """Собирает главное меню с учетом роли и функций отеля."""

    admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
    can_view_service = can_view_service_functions(
        user_id=user_id,
        admin_ids=admin_ids,
        specialist_ids=specialist_ids,
    )
    hotel_code = access_registry.get_user_hotel(user_id)
    hotel_features = set(access_registry.get_hotel_features(hotel_code))
    is_service_actor = can_view_service
    if not is_service_actor and hotel_code == "jamaica":
        return build_jamaica_main_menu_keyboard(
            can_use_wifi_help="wifi_guest_issue" in hotel_features,
        )
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


def _has_user_access(
    user_id: int,
    cfg,
    approved_user_ids: tuple[int, ...],
    banned_user_ids: tuple[int, ...],
    access_registry,
) -> bool:
    """Проверяет доступ пользователя к callback-действиям меню."""

    if user_id in set(banned_user_ids):
        return False
    admin_ids, specialist_ids, user_ids = _resolve_role_sets(cfg, access_registry)
    return can_view_user_menu(
        user_id=user_id,
        admin_ids=admin_ids,
        specialist_ids=specialist_ids,
        user_ids=user_ids,
        approved_user_ids=approved_user_ids,
    )


def register(dp) -> None:
    """Регистрирует callback-обработчики пользовательского и IT-меню."""

    cfg = get_config()
    categories = get_ticket_categories()
    user_flow = get_user_flow_service()
    tickets = get_ticket_service()
    ticket_links = get_ticket_link_service()
    clarification_sessions = get_clarification_session_service()
    close_reply_sessions = get_close_reply_session_service()
    ticket_clarifications = get_ticket_clarification_service()
    user_reply_sessions = get_user_reply_session_service()
    room_ticket_contexts = get_room_ticket_context_service()
    room_history = get_room_history_service()
    observability = get_observability_service()
    max_messages = MaxMessageService(observability=observability, retry_config=cfg.max_api)
    ticket_card_updates = TicketCardUpdateService(
        ticket_links=ticket_links,
        group_chat_id=cfg.bot.group_chat_id,
        max_messages=max_messages,
        clarifications=ticket_clarifications,
        room_contexts=room_ticket_contexts,
        observability=observability,
    )
    network_session = get_network_session_service()
    access_registry = get_user_access_registry()

    async def _start_wifi_escalation(event: MessageCallback, user_id: int) -> None:
        category = "Сеть / Wi-Fi" if "Сеть / Wi-Fi" in categories else categories[-1]
        user_flow.begin_create(user_id)
        draft = user_flow.set_category(user_id, category)
        draft.step = "awaiting_wifi_escalation_text"
        await event.message.answer(
            text=(
                f"{user_texts.WIFI_ESCALATE_TEXT}\n\n"
                "Напишите текст обращения и при необходимости добавьте фото/файл несколькими сообщениями.\n"
                "Через 20 секунд после последнего сообщения обращение отправится автоматически."
            ),
            attachments=[build_wifi_escalation_keyboard()],
        )
        await event.answer(notification="Опишите проблему для поддержки")

    async def _start_tv_escalation(event: MessageCallback, user_id: int) -> None:
        if "TV у гостя" in categories:
            category = "TV у гостя"
        elif "Телефония" in categories:
            category = "Телефония"
        else:
            category = categories[-1]
        user_flow.begin_create(user_id)
        draft = user_flow.set_category(user_id, category)
        draft.step = "awaiting_tv_escalation_text"
        await event.message.answer(
            text=(
                f"{user_texts.TV_ESCALATE_TEXT}\n\n"
                "Напишите текст обращения и при необходимости добавьте фото/файл несколькими сообщениями.\n"
                "Через 20 секунд после последнего сообщения обращение отправится автоматически."
            ),
            attachments=[build_tv_escalation_keyboard()],
        )
        await event.answer(notification="Опишите проблему TV для поддержки")

    async def _start_jamaica_room_ticket(event: MessageCallback, user_id: int) -> None:
        """Запускает ввод номера для пользователя Jamaica."""

        if room_ticket_contexts is None:
            await event.answer(notification="Справочник номеров недоступен")
            return
        hotel = room_ticket_contexts.find_user_hotel(user_id)
        if hotel is None or hotel.code != "jamaica":
            await event.answer(notification="Раздел недоступен для вашего профиля")
            return
        user_flow.begin_room_ticket(
            user_id,
            hotel_id=hotel.id,
            hotel_code=hotel.code,
        )
        await event.message.answer(
            text="Введите номер комнаты или домика.",
            attachments=[build_jamaica_cancel_keyboard()],
        )
        await event.answer(notification="Введите номер")

    async def _start_jamaica_other_ticket(event: MessageCallback, user_id: int) -> None:
        """Запускает заявку 'Прочее' без привязки к номеру."""

        if room_ticket_contexts is None:
            await event.answer(notification="Справочник номеров недоступен")
            return
        hotel = room_ticket_contexts.find_user_hotel(user_id)
        if hotel is None or hotel.code != "jamaica":
            await event.answer(notification="Раздел недоступен для вашего профиля")
            return
        category = room_ticket_contexts.find_other_category(hotel.id)
        if category is None:
            await event.answer(notification="Категория Прочее не настроена")
            return
        user_flow.begin_room_ticket_other(
            user_id,
            hotel_id=hotel.id,
            hotel_code=hotel.code,
            category_id=category.id,
            category_code=category.code,
            category_title=category.title,
        )
        await event.message.answer(
            text=(
                "Опишите проблему. Можно отправить несколько сообщений "
                "и фото/файл.\nЧерез 20 секунд после последнего сообщения "
                "обращение отправится автоматически."
            ),
            attachments=[build_jamaica_cancel_keyboard()],
        )
        await event.answer(notification="Опишите проблему")

    def _save_room_ticket_context(ticket_id: str, draft):
        """Сохраняет hotel-specific контекст заявки из callback-flow."""

        if room_ticket_contexts is None or not draft.is_room_ticket_flow:
            return None
        if not draft.hotel_id:
            return None
        return room_ticket_contexts.save_context(
            RoomTicketContext(
                ticket_key=ticket_id,
                hotel_id=draft.hotel_id,
                location_id=draft.location_id,
                issue_category_id=draft.issue_category_id,
                room_number_snapshot=draft.room_number,
                location_display_snapshot=draft.location_display,
                category_snapshot=draft.issue_category_title or draft.category,
                metadata={
                    "source": "jamaica_room_ticket_flow",
                    "hotel_code": draft.hotel_code,
                    "category_code": draft.issue_category_code,
                },
            )
        )

    async def _safe_answer(event: MessageCallback, notification: str) -> None:
        await max_messages.answer_callback(event=event, notification=notification)

    async def _replace_callback_message(event: MessageCallback, text: str, attachment) -> None:
        bot = event._ensure_bot()
        chat_id = int(event.message.recipient.chat_id)
        sent = await bot.send_message(chat_id=chat_id, text=text, attachments=[attachment])
        old_mid = getattr(getattr(event.message, "body", None), "mid", None)
        new_mid = getattr(getattr(getattr(sent, "message", None), "body", None), "mid", None)
        if old_mid and new_mid and str(old_mid) != str(new_mid):
            try:
                await bot.delete_message(message_id=old_mid)
            except Exception:
                pass

    @dp.message_callback(UserMenuPayload.filter())
    async def handle_user_menu_callback(event: MessageCallback, payload: UserMenuPayload):
        if event.message.recipient.chat_type != "dialog":
            await event.answer(notification="Меню доступно только в личном чате с ботом")
            return

        user_id = int(event.callback.user.user_id)
        action = payload.action
        logger.info("User callback received: user_id=%s action=%s", user_id, action)
        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(
            user_id,
            cfg,
            approved_user_ids,
            banned_user_ids,
            access_registry,
        ):
            logger.info("User menu denied for user_id=%s", user_id)
            await event.answer(notification="Доступ ограничен")
            return

        if action == "menu":
            user_flow.reset(user_id)
            network_session.reset(user_id)
            await event.message.answer(
                text=user_texts.WELCOME_TEXT,
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Главное меню")
            return

        if action == "network":
            is_allowed = can_use_network_tools(
                user_id=user_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            )
            if not is_allowed:
                await event.answer(notification=network_texts.NO_ACCESS_TEXT)
                return

            network_session.reset(user_id)
            await event.message.answer(
                text=network_texts.NETWORK_MENU_TEXT,
                attachments=[build_network_menu_keyboard()],
            )
            await event.answer(notification="Сетевое меню")
            return

        if action in {"jamaica_room", "jamaica_room_retry"}:
            await _start_jamaica_room_ticket(event, user_id)
            return

        if action == "jamaica_cancel":
            user_flow.reset(user_id)
            await event.message.answer(
                text=user_texts.WELCOME_TEXT,
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Отменено")
            return

        if action == "jamaica_other":
            await _start_jamaica_other_ticket(event, user_id)
            return

        if action == "jamaica_cat":
            if room_ticket_contexts is None:
                await event.answer(notification="Справочник номеров недоступен")
                return
            draft = user_flow.get(user_id)
            if draft.step != "awaiting_room_issue_category" or not draft.hotel_id:
                await event.answer(notification="Сначала введите номер")
                return
            category = None
            for item in room_ticket_contexts.list_location_categories(draft.hotel_id):
                if item.code == payload.value:
                    category = item
                    break
            if category is None:
                await event.answer(notification="Категория не найдена")
                return
            user_flow.set_room_ticket_category(
                user_id,
                category_id=category.id,
                category_code=category.code,
                category_title=category.title,
            )
            await event.message.answer(
                text=(
                    "Опишите проблему. Можно отправить несколько сообщений "
                    "и фото/файл.\nЧерез 20 секунд после последнего сообщения "
                    "обращение отправится автоматически."
                ),
                attachments=[build_jamaica_cancel_keyboard()],
            )
            await event.answer(notification="Опишите проблему")
            return

        if action == "service_help":
            await event.message.answer(
                text=(
                    "Сервисные команды для группы IT:\n"
                    "/open [N] — показать открытые заявки\n"
                    "/take <ID> — взять заявку\n"
                    "/release <ID> — освободить заявку\n"
                    "/close <ID> — закрыть заявку\n"
                    "/clarify <ID> — запросить уточнение"
                ),
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Сервисные команды")
            return

        if action == "admin_help":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            await event.message.answer(
                text=(
                    "Роль: администратор.\n"
                    "У вас есть полный доступ к сервисным действиям и override по заявкам.\n"
                    "Используйте кнопки ниже для одобрения заявок и управления пользователями."
                ),
                attachments=[build_admin_menu_keyboard()],
            )
            await event.answer(notification="Права администратора")
            return

        if action == "admin_pending":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            pending_items = access_registry.list_pending()
            if not pending_items:
                await event.message.answer("Новых заявок на доступ нет.")
                await event.answer(notification="Список заявок")
                return
            await event.message.answer(f"Заявок на доступ: {len(pending_items)}")
            for item in pending_items:
                await event.message.answer(
                    text=_build_single_pending_text(item),
                    attachments=[build_admin_request_keyboard(item.user_id)],
                )
            await event.answer(notification="Список заявок")
            return

        if action == "admin_pending_one":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return
            item = _find_pending_item(access_registry, target_user_id)
            if not item:
                await event.answer(notification="Заявка не найдена")
                return
            await event.message.edit(
                text=_build_single_pending_text(item),
                attachments=[build_admin_request_keyboard(target_user_id)],
            )
            await event.answer(notification="Заявка")
            return

        if action == "admin_approve":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return
            item = _find_pending_item(access_registry, target_user_id)
            if not item:
                await _safe_answer(event, "Заявка не найдена")
                return
            await _safe_answer(event, "Выбор роли")
            await _replace_callback_message(
                event,
                text=(
                    _build_single_pending_text(item)
                    + "\n\nВыберите роль для выдачи доступа:"
                ),
                attachment=build_admin_role_select_keyboard(target_user_id),
            )
            return

        if action in {"admin_role_user", "admin_role_it", "admin_role_admin"}:
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return

            role_map = {
                "admin_role_user": ("user", "Пользователь"),
                "admin_role_it": ("it", "IT специалист"),
                "admin_role_admin": ("admin", "Администратор"),
            }
            role_token, role_label = role_map[action]
            approve_status = access_registry.approve(target_user_id, role=role_token)
            if approve_status == "approved":
                await observability.audit(
                    action="access_approved",
                    resource_type="user",
                    resource_id=str(target_user_id),
                    result="success",
                    actor_user_id=user_id,
                    actor_role="admin",
                    metadata={"role": role_label},
                )
                await observability.audit(
                    action="role_granted",
                    resource_type="role",
                    resource_id=str(target_user_id),
                    result="success",
                    actor_user_id=user_id,
                    actor_role="admin",
                    metadata={"role": role_label},
                )
                await _safe_answer(event, f"Одобрено: {target_user_id}")
                await _replace_callback_message(
                    event,
                    text=(
                        f"Заявка обработана.\n"
                        f"ID: {target_user_id}\n"
                        f"Статус: одобрено\n"
                        f"Роль: {role_label}"
                    ),
                    attachment=build_admin_menu_keyboard(),
                )
                try:
                    await event._ensure_bot().send_message(
                        user_id=target_user_id,
                        text=(
                            "Ваша заявка одобрена.\n"
                            f"Назначена роль: {role_label}\n"
                            "Главное меню доступно ниже."
                        ),
                        attachments=[_build_menu_for_user(target_user_id, cfg, access_registry)],
                    )
                except Exception:
                    pass
                return
            if approve_status == "already_approved":
                await observability.audit(
                    action="access_approved",
                    resource_type="user",
                    resource_id=str(target_user_id),
                    result="denied",
                    actor_user_id=user_id,
                    actor_role="admin",
                    reason="already_approved",
                )
                await _safe_answer(event, "Пользователь уже одобрен")
                return
            if approve_status == "invalid_role":
                await observability.audit(
                    action="role_granted",
                    resource_type="role",
                    resource_id=str(target_user_id),
                    result="failed",
                    actor_user_id=user_id,
                    actor_role="admin",
                    reason="invalid_role",
                    metadata={"role": role_token},
                )
                await _safe_answer(event, "Некорректная роль")
                return
            await _safe_answer(event, "Заявка не найдена")
            return

        if action == "admin_reject":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return

            reject_status = access_registry.reject(target_user_id)
            if reject_status == "rejected":
                await observability.audit(
                    action="access_rejected",
                    resource_type="user",
                    resource_id=str(target_user_id),
                    result="success",
                    actor_user_id=user_id,
                    actor_role="admin",
                )
                await _safe_answer(event, f"Отклонено: {target_user_id}")
                await _replace_callback_message(
                    event,
                    text=(
                        f"Заявка обработана.\n"
                        f"ID: {target_user_id}\n"
                        "Статус: отклонено"
                    ),
                    attachment=build_admin_menu_keyboard(),
                )
                try:
                    await event._ensure_bot().send_message(
                        user_id=target_user_id,
                        text="Заявка на доступ отклонена администратором.",
                    )
                except Exception:
                    pass
            else:
                await observability.audit(
                    action="access_rejected",
                    resource_type="user",
                    resource_id=str(target_user_id),
                    result="failed",
                    actor_user_id=user_id,
                    actor_role="admin",
                    reason=reject_status,
                )
                await _safe_answer(event, "Заявка не найдена")
            return

        if action == "admin_users":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            users = access_registry.list_users()
            visible_users = [item for item in users if item.user_id not in set(admin_ids)]
            user_entries = [
                (item.user_id, item.user_name)
                for item in visible_users
            ]
            await event.message.answer(
                text=_build_users_text(visible_users),
                attachments=[build_admin_users_keyboard(user_entries)],
            )
            await event.answer(notification="Список пользователей")
            return

        if action == "admin_user_open":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return
            item = _find_user_item(access_registry, target_user_id)
            if not item:
                await event.answer(notification="Пользователь не найден")
                return
            await event.message.answer(
                text=_build_user_card_text(item, access_registry),
                attachments=[build_admin_user_actions_keyboard(target_user_id)],
            )
            await event.answer(notification="Карточка пользователя")
            return

        if action == "admin_user_hotel":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return

            item = _find_user_item(access_registry, target_user_id)
            if not item:
                await event.answer(notification="Пользователь не найден")
                return

            await event.message.answer(
                text=(
                    f"{_build_user_card_text(item, access_registry)}\n\n"
                    "Выберите отель для пользователя:"
                ),
                attachments=[
                    build_admin_hotel_select_keyboard(
                        target_user_id,
                        access_registry.list_hotels(),
                    )
                ],
            )
            await _safe_answer(event, "Выбор отеля")
            return

        if action == "admin_hotel_set":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            raw_value = (payload.value or "").strip()
            if ":" not in raw_value:
                await event.answer(notification="Некорректные данные")
                return
            raw_user_id, raw_hotel_code = raw_value.split(":", maxsplit=1)
            try:
                target_user_id = int(raw_user_id.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return

            set_status = access_registry.set_user_hotel(target_user_id, raw_hotel_code.strip())
            if set_status == "invalid_hotel":
                await _safe_answer(event, "Некорректный отель")
                return
            if set_status == "not_found":
                await _safe_answer(event, "Пользователь не найден")
                return

            item = _find_user_item(access_registry, target_user_id)
            if not item:
                await _safe_answer(event, "Пользователь не найден")
                return

            hotel_label = access_registry.get_hotel_label(item.hotel_code) or "не назначен"
            await event.message.answer(
                text=(
                    f"{_build_user_card_text(item, access_registry)}\n\n"
                    f"Текущая привязка: {hotel_label}"
                ),
                attachments=[build_admin_user_actions_keyboard(target_user_id)],
            )

            if set_status == "updated":
                await _safe_answer(event, "Отель обновлен")
                try:
                    await event._ensure_bot().send_message(
                        user_id=target_user_id,
                        text=f"Ваш профиль обновлен. Назначенный отель: {hotel_label}.",
                        attachments=[_build_menu_for_user(target_user_id, cfg, access_registry)],
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify user about hotel update: user_id=%s",
                        target_user_id,
                    )
            else:
                await _safe_answer(event, "Отель уже назначен")
            return

        if action == "admin_ban":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return

            if target_user_id in set(admin_ids):
                await event.answer(notification="Нельзя забанить администратора")
                return

            ban_status = access_registry.ban(target_user_id)
            if ban_status == "banned":
                await event.message.answer(
                    text=(
                        "Пользователь обработан.\n"
                        f"ID: {target_user_id}\n"
                        "Статус: заблокирован"
                    ),
                    attachments=[build_admin_menu_keyboard()],
                )
                await event.answer(notification=f"Заблокирован: {target_user_id}")
            elif ban_status == "already_banned":
                await event.answer(notification="Пользователь уже заблокирован")
            else:
                await event.answer(notification="Пользователь не найден")
            return

        if action == "admin_delete_user":
            if not is_admin(user_id, admin_ids):
                await event.answer(notification="Доступно только администратору")
                return
            try:
                target_user_id = int(payload.value.strip())
            except Exception:
                await event.answer(notification="Некорректный user_id")
                return

            if target_user_id in set(admin_ids):
                await event.answer(notification="Нельзя удалить администратора")
                return

            delete_status = access_registry.delete_user(target_user_id)
            if delete_status == "deleted":
                await event.message.answer(
                    text=(
                        "Пользователь обработан.\n"
                        f"ID: {target_user_id}\n"
                        "Статус: удален"
                    ),
                    attachments=[build_admin_menu_keyboard()],
                )
                await event.answer(notification=f"Удален: {target_user_id}")
            else:
                await event.answer(notification="Пользователь не найден")
            return

        if action == "create":
            logger.info("Create ticket button pressed: user_id=%s action=create", user_id)
            user_flow.begin_create(user_id)
            await event.message.answer(
                text=user_texts.CATEGORY_PROMPT,
                attachments=[build_categories_keyboard(categories)],
            )
            await event.answer(notification="Выбор категории")
            return

        if action == "cat":
            if payload.value not in categories:
                await event.answer(notification="Категория не распознана")
                return

            user_flow.set_category(user_id, payload.value)
            await event.message.answer(text=user_texts.PROBLEM_PROMPT)
            await event.answer(notification="Категория выбрана")
            return

        if action == "my":
            user_tickets = await tickets.list_user_tickets(user_id=user_id)
            lines = [user_texts.user_ticket_line(ticket) for ticket in user_tickets]
            await event.message.answer(
                text=_build_user_ticket_list_text(lines),
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Показал обращения")
            return

        if action == "ticket_reply":
            ticket_id = (payload.value or "").strip()
            ticket = await tickets.get_ticket(ticket_id)
            if ticket is None:
                await event.answer(notification="Заявка не найдена")
                return
            if ticket.user_id != user_id:
                await event.answer(notification="Ответ доступен только автору заявки")
                return
            user_reply_sessions.start(user_id=user_id, ticket_id=ticket.ticket_id)
            await event.message.answer(
                text=(
                    f"Введите ответ по заявке {ticket.ticket_id} "
                    "следующим сообщением."
                )
            )
            await event.answer(notification="Ожидаю ответ")
            logger.info(
                "User reply session started: ticket_id=%s user_id=%s",
                ticket.ticket_id,
                user_id,
            )
            return

        if action == "wifi":
            if can_view_service_functions(
                user_id=user_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await event.answer(notification="Раздел доступен только пользователям")
                return
            hotel_features = set(
                access_registry.get_hotel_features(access_registry.get_user_hotel(user_id))
            )
            if "wifi_guest_issue" not in hotel_features:
                await event.answer(notification="Раздел недоступен для вашего профиля")
                return

            await event.message.answer(
                text=user_texts.WIFI_SCOPE_TEXT,
                attachments=[build_wifi_scope_keyboard()],
            )
            await event.answer(notification="Проверка Wi-Fi")
            return

        if action == "tv_guest":
            if can_view_service_functions(
                user_id=user_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await event.answer(notification="Раздел доступен только пользователям")
                return
            hotel_features = set(
                access_registry.get_hotel_features(access_registry.get_user_hotel(user_id))
            )
            if "tv_guest_issue" not in hotel_features:
                await event.answer(notification="Раздел недоступен для вашего профиля")
                return
            await _start_tv_escalation(event, user_id)
            return

        if action == "wifi_scope_one":
            await event.message.answer(
                text=user_texts.WIFI_DEVICE_PROMPT_TEXT,
                attachments=[build_wifi_device_keyboard()],
            )
            await event.answer(notification="Выбор устройства")
            return

        if action == "wifi_scope_all":
            await _start_wifi_escalation(event, user_id)
            return

        if action == "wifi_device_mobile":
            await event.message.answer(
                text=user_texts.WIFI_MOBILE_RECOMMENDATIONS_TEXT,
                attachments=[build_wifi_auth_keyboard()],
            )
            await event.answer(notification="Рекомендации отправлены")
            return

        if action == "wifi_device_laptop":
            await event.message.answer(
                text=user_texts.WIFI_LAPTOP_RECOMMENDATIONS_TEXT,
                attachments=[build_wifi_auth_keyboard()],
            )
            await event.answer(notification="Рекомендации отправлены")
            return

        if action == "wifi_auth_yes":
            await event.message.answer(
                text=user_texts.WIFI_SURNAME_CHECK_TEXT,
                attachments=[build_wifi_resolution_keyboard()],
            )
            await event.answer(notification="Проверьте фамилию гостя")
            return

        if action == "wifi_auth_no":
            await _start_wifi_escalation(event, user_id)
            return

        if action == "wifi_resolved":
            await event.message.answer(
                text=user_texts.WIFI_RESOLVED_TEXT,
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Отлично")
            return

        if action == "wifi_unresolved":
            await _start_wifi_escalation(event, user_id)
            return

        if action == "help":
            await event.message.answer(
                text=user_texts.HELP_TEXT,
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Справка")
            return

        if action == "about":
            await event.message.answer(
                text=user_texts.ABOUT_TEXT,
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="О боте")
            return

        if action == "rewrite":
            draft = user_flow.get(user_id)
            if not draft.category:
                await event.answer(notification="Сначала выберите категорию")
                return

            draft.step = "awaiting_problem_text"
            draft.problem_text = None
            draft.attachments = []
            await event.message.answer(text=user_texts.PROBLEM_PROMPT)
            await event.answer(notification="Введите новый текст")
            return

        if action == "cancel":
            user_flow.reset(user_id)
            await event.message.answer(
                text=user_texts.CANCELLED_TEXT,
                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
            )
            await event.answer(notification="Отменено")
            return

        if action == "confirm_send":
            await _safe_answer(event, "Отправляю заявку...")
            try:
                draft = user_flow.get(user_id)
                if not draft.category or not draft.problem_text:
                    await event.message.answer(
                        text="Не хватает данных для отправки. Создайте обращение заново.",
                        attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
                    )
                    return

                sender = event.callback.user
                requester_name = get_full_name(sender, fallback="Пользователь")
                requester_phone = getattr(sender, "phone", None)
                requester_department = getattr(sender, "department", None)

                ticket = await tickets.create_ticket(
                    requester_user_id=user_id,
                    requester_name=requester_name,
                    category=draft.category,
                    text=draft.problem_text,
                    requester_phone=str(requester_phone) if requester_phone else None,
                    requester_department=str(requester_department) if requester_department else None,
                )
                logger.info(
                    "Ticket created: ticket_id=%s user_id=%s category=%s",
                    ticket.ticket_id,
                    user_id,
                    draft.category,
                )
                room_context = _save_room_ticket_context(ticket.ticket_id, draft)

                group_sent = None
                ticket_text = specialist_texts.render_group_ticket(
                    ticket,
                    room_context=room_context,
                )
                action_keyboard = build_ticket_actions_keyboard(ticket, room_context=room_context)
                media_attachments = list(draft.attachments or [])
                try:
                    group_sent = await event._ensure_bot().send_message(
                        chat_id=cfg.bot.group_chat_id,
                        text=ticket_text,
                        attachments=[*media_attachments, action_keyboard],
                        format=ParseMode.HTML,
                    )
                except Exception:
                    logger.exception(
                        "Failed to send ticket to group with media+actions: ticket_id=%s user_id=%s group_chat_id=%s",
                        ticket.ticket_id,
                        user_id,
                        cfg.bot.group_chat_id,
                    )
                    try:
                        if media_attachments:
                            group_sent = await event._ensure_bot().send_message(
                                chat_id=cfg.bot.group_chat_id,
                                text=ticket_text,
                                attachments=media_attachments,
                                format=ParseMode.HTML,
                            )
                        else:
                            group_sent = await event._ensure_bot().send_message(
                                chat_id=cfg.bot.group_chat_id,
                                text=ticket_text,
                                attachments=[action_keyboard],
                                format=ParseMode.HTML,
                            )
                    except Exception:
                        logger.exception(
                            "Failed to send ticket to group with reduced attachments: ticket_id=%s user_id=%s group_chat_id=%s",
                            ticket.ticket_id,
                            user_id,
                            cfg.bot.group_chat_id,
                        )
                        try:
                            group_sent = await event._ensure_bot().send_message(
                                chat_id=cfg.bot.group_chat_id,
                                text=ticket_text,
                                format=ParseMode.HTML,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to send ticket to group without attachments: ticket_id=%s user_id=%s group_chat_id=%s",
                                ticket.ticket_id,
                                user_id,
                                cfg.bot.group_chat_id,
                            )
                            user_flow.reset(user_id)
                            await event.message.answer(
                                text=(
                                    f"Заявка {ticket.ticket_id} сохранена, но не отправлена в группу специалистов.\n"
                                    "Проверьте MAX_GROUP_CHAT_ID и права бота в группе."
                                ),
                                attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
                            )
                            return

                if not group_sent or not getattr(group_sent, "message", None):
                    logger.error(
                        "Group send returned empty response: ticket_id=%s user_id=%s group_chat_id=%s",
                        ticket.ticket_id,
                        user_id,
                        cfg.bot.group_chat_id,
                    )
                    user_flow.reset(user_id)
                    await event.message.answer(
                        text=(
                            f"Заявка {ticket.ticket_id} сохранена, но API не подтвердил отправку в группу.\n"
                            "Проверьте MAX_GROUP_CHAT_ID и доступ бота к чату."
                        ),
                        attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
                    )
                    return

                if group_sent.message and group_sent.message.body:
                    ticket_links.bind_group_message(
                        ticket_id=ticket.ticket_id,
                        group_message_id=group_sent.message.body.mid,
                        primary=True,
                    )
                    ticket_clarifications.set_ticket_base_attachments(
                        ticket_id=ticket.ticket_id,
                        attachments=media_attachments,
                    )

                user_flow.reset(user_id)
                confirmation_mid = await max_messages.send_message(
                    bot=event._ensure_bot(),
                    user_id=user_id,
                    text=user_texts.SUBMITTED_TEXT,
                    text_format=None,
                )
                menu_sent = await event.message.answer(
                    text=user_texts.WELCOME_TEXT,
                    attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
                )
                menu_mid = _extract_message_id(menu_sent)
                user_message_id = confirmation_mid or menu_mid
                if user_message_id:
                    ticket_links.bind_user_message(
                        ticket_id=ticket.ticket_id,
                        user_message_id=user_message_id,
                    )
                return
            except Exception:
                logger.exception("Unhandled confirm_send error: user_id=%s", user_id)
                user_flow.reset(user_id)
                await event.message.answer(
                    text="Ошибка при отправке обращения. Попробуйте ещё раз.",
                    attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
                )
                return

        await event.answer(notification="Неизвестное действие")

    @dp.message_callback(ClarificationCancelPayload.filter())
    async def handle_clarification_cancel(
        event: MessageCallback,
        payload: ClarificationCancelPayload,
    ):
        """Отменяет ожидающий ввод уточнения по inline-кнопке."""

        actor_id = int(event.callback.user.user_id)
        session = clarification_sessions.get_by_ticket(payload.ticket_id)
        if session is None:
            await max_messages.answer_callback(
                event=event,
                notification="Уточнение уже отменено",
            )
            return
        if session.actor_user_id != actor_id:
            await max_messages.answer_callback(
                event=event,
                notification="Это уточнение начал другой специалист",
            )
            return

        clarification_sessions.reset(actor_id)
        await max_messages.answer_callback(
            event=event,
            notification="Запрос уточнения отменён",
        )
        deleted = await max_messages.delete_message(
            bot=event._ensure_bot(),
            message_id=session.prompt_message_id,
        )
        if deleted:
            logger.info(
                "Clarification canceled and prompt deleted: ticket_id=%s "
                "specialist_user_id=%s prompt_message_id=%s",
                session.ticket_id,
                actor_id,
                session.prompt_message_id,
            )
        else:
            logger.warning(
                "Clarification canceled but prompt delete failed: ticket_id=%s "
                "specialist_user_id=%s prompt_message_id=%s",
                session.ticket_id,
                actor_id,
                session.prompt_message_id,
            )

    @dp.message_callback(CloseReplyCancelPayload.filter())
    async def handle_close_reply_cancel(
        event: MessageCallback,
        payload: CloseReplyCancelPayload,
    ):
        """Отменяет ожидающий ввод ответа при закрытии."""

        actor_id = int(event.callback.user.user_id)
        session = close_reply_sessions.get_by_ticket(payload.ticket_id)
        if session is None:
            await max_messages.answer_callback(
                event=event,
                notification="Закрытие с ответом уже отменено",
            )
            return
        if session.actor_user_id != actor_id:
            await max_messages.answer_callback(
                event=event,
                notification="Это закрытие с ответом начал другой специалист",
            )
            return

        close_reply_sessions.cancel(actor_id)
        await observability.ticket_event(
            ticket_id=session.ticket_id,
            event_type="ticket_close_reply_cancelled",
            actor_user_id=actor_id,
            actor_name=session.actor_name,
            actor_role="IT specialist",
            source="callback",
        )
        await max_messages.answer_callback(
            event=event,
            notification="Закрытие с ответом отменено",
        )
        deleted = await max_messages.delete_message(
            bot=event._ensure_bot(),
            message_id=session.prompt_message_id,
        )
        if not deleted:
            logger.warning(
                "Close-with-reply prompt delete failed after cancel: ticket_id=%s "
                "specialist_user_id=%s prompt_message_id=%s",
                session.ticket_id,
                actor_id,
                session.prompt_message_id,
            )

    @dp.message_callback(SpecialistTicketPayload.filter())
    async def handle_specialist_ticket_callback(
        event: MessageCallback, payload: SpecialistTicketPayload
    ):
        actor = event.callback.user
        actor_id = int(actor.user_id)
        actor_name = get_full_name(actor, fallback=f"ID {actor_id}")
        action = payload.action
        ticket_id = payload.ticket_id
        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)

        if action == "open_list":
            if not can_view_service_functions(
                user_id=actor_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await event.answer(notification=specialist_texts.FORBIDDEN_TEXT)
                return
            open_tickets = await tickets.list_open_tickets(limit=50)
            attachments = [build_open_tickets_keyboard(open_tickets)] if open_tickets else None
            await event.message.answer(
                text=_build_open_tickets_text(open_tickets),
                attachments=attachments,
                format=ParseMode.HTML,
            )
            await event.answer(notification="Список открытых заявок")
            return

        if action == "open_card":
            if not can_view_service_functions(
                user_id=actor_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await event.answer(notification=specialist_texts.FORBIDDEN_TEXT)
                return
            ticket = await tickets.get_ticket(ticket_id)
            if ticket is None:
                await event.answer(notification=specialist_texts.NOT_FOUND_TEXT)
                return
            await _send_ticket_card_from_list(
                event,
                ticket,
                ticket_links,
                room_ticket_contexts,
            )
            await event.answer(notification=f"Открыта {ticket.ticket_id}")
            return

        if action == "room_history":
            if not can_view_service_functions(
                user_id=actor_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.FORBIDDEN_TEXT,
                )
                return

            room_context = room_history.get_context_by_ticket_key(ticket_id)
            if room_context is None or room_context.location_id is None:
                await max_messages.answer_callback(
                    event=event,
                    notification="История номера недоступна",
                )
                return

            try:
                items = room_history.list_recent_tickets_for_location(
                    room_context.hotel_id,
                    room_context.location_id,
                    exclude_ticket_key=ticket_id,
                    limit=ROOM_HISTORY_LIMIT,
                )
            except Exception:
                logger.exception(
                    "Failed to load room history: ticket_id=%s hotel_id=%s location_id=%s",
                    ticket_id,
                    room_context.hotel_id,
                    room_context.location_id,
                )
                await max_messages.answer_callback(
                    event=event,
                    notification="Историю номера получить не удалось",
                )
                return

            await event.message.answer(
                text=room_history_texts.render_room_history(
                    room_context=room_context,
                    items=items,
                ),
                format=ParseMode.HTML,
            )
            await max_messages.answer_callback(
                event=event,
                notification="История номера отправлена",
            )
            return

        if action == "attach_reply":
            if not can_view_service_functions(
                user_id=actor_id,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.FORBIDDEN_TEXT,
                )
                return

            ticket = await tickets.get_ticket(ticket_id)
            if ticket is None:
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.NOT_FOUND_TEXT,
                )
                return

            body = getattr(event.message, "body", None)
            group_message_id = getattr(body, "mid", None)
            attached_reply = None
            if group_message_id:
                attached_reply = ticket_clarifications.attach_user_reply(str(group_message_id))
            if attached_reply is None or attached_reply.ticket_id != ticket.ticket_id:
                await max_messages.answer_callback(
                    event=event,
                    notification="Ответ не найден для прикрепления",
                )
                return

            ticket_for_card = ticket
            if ticket.status == TicketStatus.WAITING_USER:
                status_result = await tickets.set_ticket_status(
                    ticket_id=ticket.ticket_id,
                    status=TicketStatus.IN_PROGRESS.value,
                )
                if status_result.ok and status_result.ticket is not None:
                    ticket_for_card = status_result.ticket
                else:
                    logger.warning(
                        "Failed to move ticket back to in_progress after user reply: "
                        "ticket_id=%s reason=%s",
                        ticket.ticket_id,
                        status_result.reason,
                    )

            card_updated = await ticket_card_updates.update_group_ticket_card(
                bot=event._ensure_bot(),
                ticket=ticket_for_card,
                notify=False,
            )
            await observability.ticket_event(
                ticket_id=ticket.ticket_id,
                event_type="user_reply_attached_to_card",
                actor_user_id=actor_id,
                actor_name=actor_name,
                actor_role="IT specialist",
                source="callback",
                related_message_id=str(group_message_id) if group_message_id else None,
                metadata={"card_updated": card_updated},
            )
            await max_messages.answer_callback(
                event=event,
                notification=(
                    "Ответ прикреплён к карточке"
                    if card_updated
                    else "Ответ сохранён, карточку не удалось обновить"
                ),
            )
            deleted = await max_messages.delete_message(
                bot=event._ensure_bot(),
                message_id=str(group_message_id) if group_message_id else None,
            )
            logger.info(
                "User reply attached to card: ticket_id=%s actor_id=%s "
                "group_message_id=%s card_updated=%s message_deleted=%s",
                ticket.ticket_id,
                actor_id,
                group_message_id,
                card_updated,
                deleted,
            )
            return

        if action == "take" and not can_take_ticket(
            user_id=actor_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            await observability.audit(
                action="access_denied",
                resource_type="ticket",
                resource_id=ticket_id,
                result="denied",
                actor_user_id=actor_id,
                actor_role="unknown",
                reason="cannot_take_ticket",
            )
            await max_messages.answer_callback(
                event=event,
                notification=specialist_texts.FORBIDDEN_TEXT,
            )
            return

        if action in {"release", "close", "clarify", "close_with_reply"}:
            ticket = await tickets.get_ticket(ticket_id)
            if ticket is None:
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.NOT_FOUND_TEXT,
                )
                return
            if not can_change_ticket_status(
                actor_user_id=actor_id,
                ticket=ticket,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await observability.audit(
                    action="access_denied",
                    resource_type="ticket",
                    resource_id=ticket_id,
                    result="denied",
                    actor_user_id=actor_id,
                    actor_role="unknown",
                    reason=f"cannot_{action}_ticket",
                )
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.FORBIDDEN_TEXT,
                )
                return

            if action == "clarify":
                existing_session = clarification_sessions.get_by_ticket(ticket.ticket_id)
                if existing_session and existing_session.actor_user_id != actor_id:
                    await max_messages.answer_callback(
                        event=event,
                        notification="Уточнение уже начал другой специалист",
                    )
                    return

                previous_session = clarification_sessions.get(actor_id)
                if previous_session and previous_session.prompt_message_id:
                    await max_messages.delete_message(
                        bot=event._ensure_bot(),
                        message_id=previous_session.prompt_message_id,
                    )

                session = clarification_sessions.start(
                    actor_user_id=actor_id,
                    actor_name=actor_name,
                    ticket_id=ticket.ticket_id,
                    group_chat_id=cfg.bot.group_chat_id,
                )
                await max_messages.answer_callback(
                    event=event,
                    notification=(
                        "Введите вопрос для пользователя следующим сообщением"
                    ),
                )
                prompt_sent = await event.message.answer(
                    "Введите вопрос для пользователя по заявке "
                    f"{ticket.ticket_id} следующим сообщением "
                    "в этом чате.",
                    attachments=[
                        build_clarification_cancel_keyboard(ticket.ticket_id)
                    ],
                )
                prompt_message_id = _extract_message_id(prompt_sent)
                clarification_sessions.set_prompt_message_id(actor_id, prompt_message_id)
                logger.info(
                    "Clarification session started: ticket_id=%s specialist_user_id=%s "
                    "prompt_message_id=%s session_id=%s",
                    ticket.ticket_id,
                    actor_id,
                    prompt_message_id,
                    session.session_id,
                )
                return

            if action == "close_with_reply":
                if ticket.status == TicketStatus.CLOSED:
                    await max_messages.answer_callback(
                        event=event,
                        notification=specialist_texts.ALREADY_CLOSED_TEXT,
                    )
                    return
                existing_session = close_reply_sessions.get_by_ticket(ticket.ticket_id)
                if existing_session and existing_session.actor_user_id != actor_id:
                    await max_messages.answer_callback(
                        event=event,
                        notification="Закрытие с ответом уже начал другой специалист",
                    )
                    return
                previous_session = close_reply_sessions.get(actor_id)
                if previous_session and previous_session.prompt_message_id:
                    await max_messages.delete_message(
                        bot=event._ensure_bot(),
                        message_id=previous_session.prompt_message_id,
                    )
                session = close_reply_sessions.start(
                    actor_user_id=actor_id,
                    actor_name=actor_name,
                    ticket_id=ticket.ticket_id,
                    group_chat_id=cfg.bot.group_chat_id,
                )
                await max_messages.answer_callback(
                    event=event,
                    notification="Введите сообщение пользователю следующим сообщением",
                )
                prompt_sent = await event.message.answer(
                    "Введите сообщение пользователю о выполненной работе.",
                    attachments=[build_close_reply_cancel_keyboard(ticket.ticket_id)],
                )
                prompt_message_id = _extract_message_id(prompt_sent)
                close_reply_sessions.set_prompt_message_id(actor_id, prompt_message_id)
                await observability.ticket_event(
                    ticket_id=ticket.ticket_id,
                    event_type="ticket_close_reply_started",
                    actor_user_id=actor_id,
                    actor_name=actor_name,
                    actor_role="IT specialist",
                    source="callback",
                )
                logger.info(
                    "Close-with-reply session started: ticket_id=%s specialist_user_id=%s "
                    "prompt_message_id=%s session_id=%s",
                    ticket.ticket_id,
                    actor_id,
                    prompt_message_id,
                    session.session_id,
                )
                return

        if action == "take":
            result = await tickets.take_ticket(
                ticket_id=ticket_id,
                specialist_user_id=actor_id,
                specialist_name=actor_name,
            )
        elif action == "release":
            result = await tickets.release_ticket(
                ticket_id=ticket_id,
                actor_user_id=actor_id,
                admin_ids=admin_ids,
            )
        elif action == "close":
            result = await tickets.close_ticket(
                ticket_id=ticket_id,
                actor_user_id=actor_id,
                actor_name=actor_name,
                admin_ids=admin_ids,
            )
        else:
            await max_messages.answer_callback(event=event, notification="Неизвестное действие")
            return

        if not result.ok or result.ticket is None:
            if result.reason == "already_assigned":
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.ALREADY_ASSIGNED_TEXT,
                )
            elif result.reason == "forbidden":
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.FORBIDDEN_TEXT,
                )
            elif result.reason == "already_closed":
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.ALREADY_CLOSED_TEXT,
                )
            elif result.reason == "not_assigned":
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.NOT_ASSIGNED_TEXT,
                )
            else:
                await max_messages.answer_callback(
                    event=event,
                    notification=specialist_texts.NOT_FOUND_TEXT,
                )
            return

        logger.info(
            "Ticket updated via callback: actor=%s ticket_id=%s action=%s status=%s",
            actor_id,
            result.ticket.ticket_id,
            action,
            result.ticket.status.value,
        )
        action_notifications = {
            "take": "Заявка назначена на вас",
            "release": "Заявка освобождена",
            "close": "Заявка закрыта",
        }
        notification = action_notifications.get(action, "Статус обновлён")
        await ticket_card_updates.update_group_ticket_card_from_callback(
            event=event,
            ticket=result.ticket,
            notification=notification,
            notify=False,
        )
        if action == "close":
            await notify_user_ticket_closed(event._ensure_bot(), result.ticket)
