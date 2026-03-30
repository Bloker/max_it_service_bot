from maxapi.types import Command, MessageCreated

from app.admin.services.access_service import can_use_network_tools, can_view_user_menu
from app.common.user_helpers import get_first_name
from app.helpdesk.keyboards.helpdesk_keyboards import build_main_menu_keyboard
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


def register(dp) -> None:
    cfg = get_config()
    user_flow = get_user_flow_service()
    network_session = get_network_session_service()
    tickets = get_ticket_service()

    @dp.message_created(Command("start"))
    async def cmd_start(event: MessageCreated):
        user = event.message.sender
        name = get_first_name(user, fallback="друг")
        user_id = int(getattr(user, "user_id"))
        if not can_view_user_menu(user_id):
            return

        user_flow.reset(user_id)
        network_session.reset(user_id)
        await event.message.answer(
            text=START_TEXT_TEMPLATE.format(name=name),
            attachments=[build_main_menu_keyboard()],
        )

    @dp.message_created(Command("menu"))
    async def cmd_menu(event: MessageCreated):
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        if not can_view_user_menu(user_id):
            return

        user_flow.reset(user_id)
        network_session.reset(user_id)
        await event.message.answer(
            text=user_texts.WELCOME_TEXT,
            attachments=[build_main_menu_keyboard()],
        )

    @dp.message_created(Command("my"))
    async def cmd_my(event: MessageCreated):
        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        if not can_view_user_menu(user_id):
            return

        user_tickets = await tickets.list_user_tickets(user_id=user_id)
        if not user_tickets:
            text = user_texts.NO_TICKETS_TEXT
        else:
            lines = [user_texts.user_ticket_line(ticket) for ticket in user_tickets]
            text = f"{user_texts.MY_TICKETS_HEADER}\n" + "\n".join(lines)

        await event.message.answer(
            text=text,
            attachments=[build_main_menu_keyboard()],
        )

    @dp.message_created(Command("network"))
    async def cmd_network(event: MessageCreated):
        if event.message.recipient.chat_type != "dialog":
            return

        user = event.message.sender
        user_id = int(getattr(user, "user_id"))
        is_allowed = can_use_network_tools(
            user_id=user_id,
            admin_ids=cfg.bot.admin_ids,
            specialist_ids=cfg.bot.it_specialist_ids,
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
        user_id = int(getattr(event.message.sender, "user_id"))
        if not can_view_user_menu(user_id):
            return

        await event.message.answer(
            text=_build_help_text(),
            attachments=[build_main_menu_keyboard()],
        )
