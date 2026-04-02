from maxapi.types import Command, MessageCreated

from app.admin.runtime import get_user_access_registry
from app.admin.services.access_service import (
    can_use_network_tools,
    can_view_service_functions,
    can_view_user_menu,
    is_admin,
)
from app.common.user_helpers import get_first_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_main_menu_keyboard,
    build_registration_keyboard,
)
from app.helpdesk.runtime import get_ticket_service, get_user_flow_service
from app.helpdesk.services.menu_service import get_helpdesk_commands
from app.helpdesk.texts import user_texts
from app.network.keyboards.network_keyboards import build_network_menu_keyboard
from app.network.runtime import get_network_session_service
from app.network.texts import network_texts
from config.config import get_config


START_TEXT_TEMPLATE = "👋 Привет, {name}!\n\nIT Help Desk готов принять обращение."


def _build_help_text() -> str:
    commands = get_helpdesk_commands()
    commands_lines = [f"• {command}" for command in commands]
    commands_block = "\n".join(commands_lines)

    return (
        "📋 **Доступные команды:**\n\n"
        f"{commands_block}\n\n"
        "Используйте меню для создания и отслеживания обращений."
    )


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
    return build_main_menu_keyboard(
        can_use_network_tools=can_use_network_tools(
            user_id=user_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ),
        can_view_service_functions=can_view_service,
        is_admin=is_admin(user_id, admin_ids),
        can_use_wifi_help=not can_view_service,
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


def _denied_text() -> str:
    return (
        "Доступ к боту ограничен.\n"
        "Нажмите кнопку ниже и поделитесь контактом для регистрации."
    )


async def _require_dialog(event: MessageCreated) -> bool:
    if event.message.recipient.chat_type == "dialog":
        return True
    await event.message.answer("Эта команда доступна только в личном чате с ботом.")
    return False


def register(dp) -> None:
    cfg = get_config()
    access_registry = get_user_access_registry()
    user_flow = get_user_flow_service()
    network_session = get_network_session_service()
    tickets = get_ticket_service()

    @dp.message_created(Command("start"))
    async def cmd_start(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        name = get_first_name(user, fallback="друг")
        user_id = int(getattr(user, "user_id"))
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(user_id, cfg, approved_user_ids, banned_user_ids, access_registry):
            await event.message.answer(
                _denied_text(),
                attachments=[build_registration_keyboard()],
            )
            return

        user_flow.reset(user_id)
        network_session.reset(user_id)
        await event.message.answer(
            text=START_TEXT_TEMPLATE.format(name=name),
            attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
        )

    @dp.message_created(Command("menu"))
    async def cmd_menu(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(user_id, cfg, approved_user_ids, banned_user_ids, access_registry):
            await event.message.answer(
                _denied_text(),
                attachments=[build_registration_keyboard()],
            )
            return

        user_flow.reset(user_id)
        network_session.reset(user_id)
        await event.message.answer(
            text=user_texts.WELCOME_TEXT,
            attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
        )

    @dp.message_created(Command("my"))
    async def cmd_my(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(user_id, cfg, approved_user_ids, banned_user_ids, access_registry):
            await event.message.answer(
                _denied_text(),
                attachments=[build_registration_keyboard()],
            )
            return

        user_tickets = await tickets.list_user_tickets(user_id=user_id)
        if not user_tickets:
            text = user_texts.NO_TICKETS_TEXT
        else:
            lines = [user_texts.user_ticket_line(ticket) for ticket in user_tickets]
            text = f"{user_texts.MY_TICKETS_HEADER}\n" + "\n".join(lines)

        await event.message.answer(
            text=text,
            attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
        )

    @dp.message_created(Command("network"))
    async def cmd_network(event: MessageCreated):
        if not await _require_dialog(event):
            return

        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        is_allowed = can_use_network_tools(
            user_id=user_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        )
        if not is_allowed:
            await event.message.answer(network_texts.NO_ACCESS_TEXT)
            return

        network_session.reset(user_id)
        await event.message.answer(
            text=network_texts.NETWORK_MENU_TEXT,
            attachments=[build_network_menu_keyboard()],
        )

    @dp.message_created(Command("help"))
    async def cmd_help(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user_id = int(getattr(event.message.sender, "user_id"))
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(user_id, cfg, approved_user_ids, banned_user_ids, access_registry):
            await event.message.answer(
                _denied_text(),
                attachments=[build_registration_keyboard()],
            )
            return

        await event.message.answer(
            text=_build_help_text(),
            attachments=[_build_menu_for_user(user_id, cfg, access_registry)],
        )

    @dp.message_created(Command("group"))
    async def cmd_group(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        if not can_view_service_functions(
            user_id=user_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            await event.message.answer("Команда доступна только IT specialist/admin.")
            return

        bot = event._ensure_bot()
        configured_group_id = cfg.bot.group_chat_id
        try:
            chat = await bot.get_chat_by_id(configured_group_id)
            chat_title = getattr(chat, "title", None) or getattr(chat, "name", None) or "-"
            chat_type = getattr(chat, "type", None) or "-"
            member_info = await bot.get_me_from_chat(configured_group_id)
            is_admin_in_chat = bool(getattr(member_info, "is_admin", False))
            await event.message.answer(
                "Проверка group chat:\n"
                f"configured MAX_GROUP_CHAT_ID={configured_group_id}\n"
                f"chat.title={chat_title}\n"
                f"chat.type={chat_type}\n"
                f"bot.is_admin={is_admin_in_chat}"
            )
        except Exception as exc:
            await event.message.answer(
                "Не удалось получить доступ к configured group chat.\n"
                f"MAX_GROUP_CHAT_ID={configured_group_id}\n"
                f"Ошибка: {exc}"
            )

    @dp.message_created(Command("register"))
    async def cmd_register(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if _has_user_access(user_id, cfg, approved_user_ids, banned_user_ids, access_registry):
            await event.message.answer("Доступ уже активен. Используйте /menu")
            return

        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        if not admin_ids:
            await event.message.answer("В системе не настроены администраторы. Обратитесь в IT.")
            return

        await event.message.answer(
            "Для регистрации нажмите кнопку и поделитесь контактом.",
            attachments=[build_registration_keyboard()],
        )

    @dp.message_created(Command("pending"))
    async def cmd_pending(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        if not is_admin(user_id, admin_ids):
            await event.message.answer("Команда доступна только admin.")
            return

        pending = access_registry.list_pending()
        if not pending:
            await event.message.answer("Новых заявок нет.")
            return

        lines = ["Заявки на доступ:"]
        for idx, item in enumerate(pending):
            requested_at = str(item.requested_at or "")
            requested_at = requested_at.replace("T", " ")
            requested_at = requested_at.split("+", maxsplit=1)[0]
            requested_at = requested_at.split(".", maxsplit=1)[0]
            lines.append(f"{item.user_id} | {item.user_name}")
            lines.append(f"Телефон: {item.phone or '-'}")
            lines.append(requested_at)
            if idx < len(pending) - 1:
                lines.append("")
        await event.message.answer("\n".join(lines))

    @dp.message_created(Command("approve"))
    async def cmd_approve(event: MessageCreated):
        if not await _require_dialog(event):
            return
        user = event.message.sender
        actor_id = int(getattr(user, "user_id"))
        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        if not is_admin(actor_id, admin_ids):
            await event.message.answer("Команда доступна только admin.")
            return

        raw_text = (event.message.body.text or "").strip()
        parts = raw_text.split()
        if len(parts) < 2:
            await event.message.answer("Формат: /approve <user_id> [user|it|admin]")
            return

        try:
            target_user_id = int(parts[1].strip())
        except ValueError:
            await event.message.answer("user_id должен быть числом.")
            return

        role = parts[2].strip() if len(parts) > 2 else "user"
        status = access_registry.approve(target_user_id, role=role)
        if status == "not_found":
            await event.message.answer("Заявка не найдена. Проверьте /pending.")
            return
        if status == "invalid_role":
            await event.message.answer("Роль должна быть: user, it или admin.")
            return
        if status == "already_approved":
            await event.message.answer("Пользователь уже одобрен.")
            return

        role_map = {"user": "user", "it": "IT specialist", "admin": "admin"}
        role_label = role_map.get(role.lower(), role)
        await event.message.answer(f"Доступ выдан пользователю {target_user_id}. Роль: {role_label}.")
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

    @dp.message_created(Command("users"))
    async def cmd_users(event: MessageCreated):
        if not await _require_dialog(event):
            return
        actor_id = int(getattr(event.message.sender, "user_id"))
        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        if not is_admin(actor_id, admin_ids):
            await event.message.answer("Команда доступна только admin.")
            return

        users = access_registry.list_users()
        if not users:
            await event.message.answer("Пользователей в базе нет.")
            return

        lines = ["Пользователи:"]
        for idx, item in enumerate(users):
            lines.append(f"ID: {item.user_id}")
            lines.append(f"Имя: {item.user_name}")
            lines.append(f"Телефон: {item.phone or '-'}")
            lines.append(f"Роль: {item.role}")
            lines.append(f"Статус: {item.status}")
            if idx < len(users) - 1:
                lines.append("")
        await event.message.answer("\n".join(lines))

    @dp.message_created(Command("ban"))
    async def cmd_ban(event: MessageCreated):
        if not await _require_dialog(event):
            return
        actor_id = int(getattr(event.message.sender, "user_id"))
        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        if not is_admin(actor_id, admin_ids):
            await event.message.answer("Команда доступна только admin.")
            return

        parts = (event.message.body.text or "").strip().split()
        if len(parts) < 2:
            await event.message.answer("Формат: /ban <user_id>")
            return
        try:
            target_user_id = int(parts[1].strip())
        except ValueError:
            await event.message.answer("user_id должен быть числом.")
            return
        if target_user_id in set(admin_ids):
            await event.message.answer("Нельзя забанить администратора.")
            return

        status = access_registry.ban(target_user_id)
        if status == "banned":
            await event.message.answer(f"Пользователь {target_user_id} заблокирован.")
            return
        if status == "already_banned":
            await event.message.answer("Пользователь уже заблокирован.")
            return
        await event.message.answer("Пользователь не найден.")

    @dp.message_created(Command("delete_user"))
    async def cmd_delete_user(event: MessageCreated):
        if not await _require_dialog(event):
            return
        actor_id = int(getattr(event.message.sender, "user_id"))
        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        if not is_admin(actor_id, admin_ids):
            await event.message.answer("Команда доступна только admin.")
            return

        parts = (event.message.body.text or "").strip().split()
        if len(parts) < 2:
            await event.message.answer("Формат: /delete_user <user_id>")
            return
        try:
            target_user_id = int(parts[1].strip())
        except ValueError:
            await event.message.answer("user_id должен быть числом.")
            return
        if target_user_id in set(admin_ids):
            await event.message.answer("Нельзя удалить администратора.")
            return

        status = access_registry.delete_user(target_user_id)
        if status == "deleted":
            await event.message.answer(f"Пользователь {target_user_id} удален.")
            return
        await event.message.answer("Пользователь не найден.")
