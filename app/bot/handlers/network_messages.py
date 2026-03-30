import logging

from maxapi.types import MessageCreated

from app.admin.services.access_service import can_use_network_tools
from app.network.keyboards.network_keyboards import build_network_menu_keyboard
from app.network.runtime import get_network_session_service, get_network_tools_service
from app.network.texts import network_texts
from config.config import get_config

logger = logging.getLogger(__name__)


def register(dp) -> None:
    cfg = get_config()
    network_tools = get_network_tools_service()
    network_session = get_network_session_service()

    @dp.message_created()
    async def handle_network_target_input(event: MessageCreated):
        text = (event.message.body.text or "").strip()
        if not text:
            return

        actor_id = event.message.sender.user_id
        is_allowed = can_use_network_tools(
            user_id=actor_id,
            admin_ids=cfg.bot.admin_ids,
            specialist_ids=cfg.bot.it_specialist_ids,
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
            result = await network_tools.run_tool(tool, target)
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

        logger.info(
            "Network target received: user_id=%s tool=%s target=%s",
            actor_id,
            session.pending_tool,
            text,
        )
        result = await network_tools.run_tool(session.pending_tool, text)
        network_session.mark_processed(actor_id)
        await event.message.answer(
            text=network_texts.render_result(result.title, result.ok, result.details),
            attachments=[build_network_menu_keyboard()],
        )
