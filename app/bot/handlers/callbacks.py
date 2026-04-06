import logging

from maxapi.enums.parse_mode import ParseMode
from maxapi.types import MessageCallback

from app.admin.runtime import get_user_access_registry
from app.admin.services.access_service import (
    can_change_ticket_status,
    can_take_ticket,
    can_use_network_tools,
    can_view_service_functions,
    can_view_user_menu,
    is_admin,
)
from app.common.user_helpers import get_full_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_admin_hotel_select_keyboard,
    build_admin_menu_keyboard,
    build_admin_request_keyboard,
    build_admin_role_select_keyboard,
    build_admin_user_actions_keyboard,
    build_admin_users_keyboard,
    build_categories_keyboard,
    build_main_menu_keyboard,
    build_ticket_actions_keyboard,
    build_wifi_auth_keyboard,
    build_wifi_device_keyboard,
    build_wifi_escalation_keyboard,
    build_wifi_resolution_keyboard,
    build_wifi_scope_keyboard,
    build_tv_escalation_keyboard,
)
from app.helpdesk.payloads import SpecialistTicketPayload, UserMenuPayload
from app.helpdesk.runtime import (
    get_ticket_link_service,
    get_ticket_service,
    get_user_flow_service,
)
from app.helpdesk.services.menu_service import get_ticket_categories
from app.helpdesk.texts import specialist_texts, user_texts
from app.network.keyboards.network_keyboards import build_network_menu_keyboard
from app.network.runtime import get_network_session_service
from app.network.texts import network_texts
from config.config import get_config

logger = logging.getLogger(__name__)


def _build_user_ticket_list_text(lines: list[str]) -> str:
    if not lines:
        return user_texts.NO_TICKETS_TEXT
    return f"{user_texts.MY_TICKETS_HEADER}\n" + "\n".join(lines)


def _build_single_pending_text(item) -> str:
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
    for item in access_registry.list_pending():
        if item.user_id == user_id:
            return item
    return None


def _build_users_text(users) -> str:
    if not users:
        return "Пользователей в базе нет."
    lines = ["Список пользователей:"]
    for idx, item in enumerate(users):
        lines.append(f"{item.user_id} | {item.user_name}")
        if idx < len(users) - 1:
            lines.append("")
    return "\n".join(lines)


def _build_open_tickets_text(items) -> str:
    if not items:
        return "Открытых заявок нет."
    lines = ["Не закрытые заявки:"]
    for ticket in items:
        assignee = ticket.assignee_name or "не назначен"
        lines.append(
            f"{ticket.ticket_id} | {ticket.status.value} | {assignee} | {ticket.category}"
        )
    return "\n".join(lines)


def _build_user_card_text(item, access_registry) -> str:
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
    for item in access_registry.list_users():
        if item.user_id == user_id:
            return item
    return None


def _resolve_role_sets(cfg, access_registry):
    admin_ids = set(cfg.bot.admin_ids) | set(access_registry.get_ids_by_role("admin"))
    specialist_ids = set(cfg.bot.it_specialist_ids) | set(
        access_registry.get_ids_by_role("IT specialist")
    )
    user_ids = set(cfg.bot.user_ids) | set(access_registry.get_ids_by_role("user"))
    return tuple(admin_ids), tuple(specialist_ids), tuple(user_ids)


def _build_menu_for_user(user_id: int, cfg, access_registry):
    admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
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
        can_view_my_tickets=is_service_actor,
        can_view_help=is_service_actor,
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
    cfg = get_config()
    categories = get_ticket_categories()
    user_flow = get_user_flow_service()
    tickets = get_ticket_service()
    ticket_links = get_ticket_link_service()
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

    async def _safe_answer(event: MessageCallback, notification: str) -> None:
        try:
            await event.answer(notification=notification)
        except Exception:
            logger.exception("Failed to send callback answer: notification=%s", notification)

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
                            "Используйте /start или /menu."
                        ),
                        attachments=[_build_menu_for_user(target_user_id, cfg, access_registry)],
                    )
                except Exception:
                    pass
                return
            if approve_status == "already_approved":
                await _safe_answer(event, "Пользователь уже одобрен")
                return
            if approve_status == "invalid_role":
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

                group_sent = None
                ticket_text = specialist_texts.render_group_ticket(ticket)
                action_keyboard = build_ticket_actions_keyboard(ticket.ticket_id)
                media_attachments = list(draft.attachments or [])
                try:
                    group_sent = await event._ensure_bot().send_message(
                        chat_id=cfg.bot.group_chat_id,
                        text=ticket_text,
                        attachments=[*media_attachments, action_keyboard],
                        parse_mode=ParseMode.HTML,
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
                                parse_mode=ParseMode.HTML,
                            )
                        else:
                            group_sent = await event._ensure_bot().send_message(
                                chat_id=cfg.bot.group_chat_id,
                                text=ticket_text,
                                attachments=[action_keyboard],
                                parse_mode=ParseMode.HTML,
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
                                parse_mode=ParseMode.HTML,
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

                user_flow.reset(user_id)
                user_sent = await event.message.answer(
                    text=user_texts.SUBMITTED_TEXT,
                    attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
                )
                if user_sent and getattr(user_sent, "message", None) and user_sent.message.body:
                    ticket_links.bind_user_message(
                        ticket_id=ticket.ticket_id,
                        user_message_id=user_sent.message.body.mid,
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
            await event.message.answer(text=_build_open_tickets_text(open_tickets))
            await event.answer(notification="Список открытых заявок")
            return

        if action == "take" and not can_take_ticket(
            user_id=actor_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            await event.answer(notification=specialist_texts.FORBIDDEN_TEXT)
            return

        if action in {"release", "close", "clarify"}:
            ticket = await tickets.get_ticket(ticket_id)
            if ticket is None:
                await event.answer(notification=specialist_texts.NOT_FOUND_TEXT)
                return
            if not can_change_ticket_status(
                actor_user_id=actor_id,
                ticket=ticket,
                admin_ids=admin_ids,
                specialist_ids=specialist_ids,
            ):
                await event.answer(notification=specialist_texts.FORBIDDEN_TEXT)
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
        elif action == "clarify":
            result = await tickets.request_clarification(
                ticket_id=ticket_id,
                actor_user_id=actor_id,
                actor_name=actor_name,
                admin_ids=admin_ids,
            )
        else:
            await event.answer(notification="Неизвестное действие")
            return

        if not result.ok or result.ticket is None:
            if result.reason == "already_assigned":
                await event.answer(notification=specialist_texts.ALREADY_ASSIGNED_TEXT)
            elif result.reason == "forbidden":
                await event.answer(notification=specialist_texts.FORBIDDEN_TEXT)
            elif result.reason == "already_closed":
                await event.answer(notification=specialist_texts.ALREADY_CLOSED_TEXT)
            elif result.reason == "not_assigned":
                await event.answer(notification=specialist_texts.NOT_ASSIGNED_TEXT)
            else:
                await event.answer(notification=specialist_texts.NOT_FOUND_TEXT)
            return

        logger.info(
            "Ticket updated via callback: actor=%s ticket_id=%s action=%s status=%s",
            actor_id,
            result.ticket.ticket_id,
            action,
            result.ticket.status.value,
        )
        await event.message.edit(
            text=specialist_texts.render_group_ticket(result.ticket),
            attachments=[build_ticket_actions_keyboard(result.ticket.ticket_id)],
            parse_mode=ParseMode.HTML,
        )
        await event.answer(notification="Статус обновлён")
