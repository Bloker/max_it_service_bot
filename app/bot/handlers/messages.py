import logging

from maxapi.types import BotStarted, MessageCreated

from app.admin.services.access_service import (
    can_change_ticket_status,
    can_take_ticket,
    can_use_network_tools,
    can_view_service_functions,
)
from app.common.user_helpers import get_first_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_confirm_keyboard,
    build_main_menu_keyboard,
    build_ticket_actions_keyboard,
)
from app.helpdesk.runtime import (
    get_ticket_link_service,
    get_ticket_service,
    get_user_flow_service,
)
from app.helpdesk.services.menu_service import get_ticket_categories
from app.helpdesk.services.ticket_service import (
    get_optional_contact_details,
    get_sender_identity,
    is_command_text,
    normalize_ticket_id,
    normalize_ticket_text,
    parse_specialist_command,
)
from app.helpdesk.texts import specialist_texts, user_texts
from app.network.runtime import get_network_session_service
from config.config import get_config

logger = logging.getLogger(__name__)


def _resolve_replied_mid(event: MessageCreated) -> str | None:
    linked = event.message.link
    if not linked or not linked.message:
        return None
    return linked.message.mid


def _render_open_tickets(lines: list[str]) -> str:
    if not lines:
        return "Открытых заявок нет."
    return "Открытые заявки:\n" + "\n".join(lines)


def register(dp) -> None:
    cfg = get_config()
    categories = get_ticket_categories()
    tickets = get_ticket_service()
    ticket_links = get_ticket_link_service()
    user_flow = get_user_flow_service()
    network_session = get_network_session_service()
    group_chat_id = cfg.bot.group_chat_id

    @dp.bot_started()
    async def handle_bot_started(event: BotStarted):
        user = event.user
        name = get_first_name(user, fallback="друг")

        await event.bot.send_message(
            chat_id=event.chat_id,
            text=(
                f"👋 Привет, {name}!\n\n"
                "Используйте меню, чтобы создать обращение в IT Help Desk."
            ),
            attachments=[build_main_menu_keyboard()],
        )

    @dp.message_created()
    async def handle_all_messages(event: MessageCreated):
        if event.message.recipient.chat_type != "dialog":
            if event.message.recipient.chat_id != group_chat_id:
                return

            text = normalize_ticket_text(event.message.body.text, "")
            if not text.startswith("/"):
                return

            actor = event.message.sender
            actor_id, actor_name = get_sender_identity(actor, fallback_name="Специалист")

            if text.startswith("/open"):
                if not can_view_service_functions(
                    user_id=actor_id,
                    admin_ids=cfg.bot.admin_ids,
                    specialist_ids=cfg.bot.it_specialist_ids,
                ):
                    logger.info("Open queue denied for user_id=%s", actor_id)
                    await event.message.answer(specialist_texts.FORBIDDEN_TEXT)
                    return

                parts = text.split(maxsplit=1)
                limit = 10
                if len(parts) > 1 and parts[1].isdigit():
                    limit = max(1, min(int(parts[1]), 50))

                open_tickets = await tickets.list_open_tickets(limit=limit)
                logger.info(
                    "Open queue requested: actor=%s limit=%s found=%s",
                    actor_id,
                    limit,
                    len(open_tickets),
                )
                lines = []
                for ticket in open_tickets:
                    assignee = ticket.assignee_name or "не назначен"
                    lines.append(
                        f"{ticket.ticket_id} | {ticket.status.value} | {assignee} | {ticket.category}"
                    )
                await event.message.answer(_render_open_tickets(lines))
                return

            action, maybe_ticket_id = parse_specialist_command(text)
            if not action:
                return

            ticket_id = maybe_ticket_id
            if not ticket_id:
                reply_mid = _resolve_replied_mid(event)
                if reply_mid:
                    ticket_id = ticket_links.get_ticket_id_by_group_message(reply_mid)

            if not ticket_id:
                await event.message.answer(
                    "Укажите ID заявки, например: /take T-00001\n"
                    "Или используйте reply к сообщению заявки."
                )
                return

            ticket_id = normalize_ticket_id(ticket_id)
            if action == "take":
                if not can_take_ticket(
                    user_id=actor_id,
                    admin_ids=cfg.bot.admin_ids,
                    specialist_ids=cfg.bot.it_specialist_ids,
                ):
                    logger.info("Take denied by role: actor=%s ticket_id=%s", actor_id, ticket_id)
                    await event.message.answer(specialist_texts.FORBIDDEN_TEXT)
                    return
                result = await tickets.take_ticket(
                    ticket_id=ticket_id,
                    specialist_user_id=actor_id,
                    specialist_name=actor_name,
                )
            elif action in {"release", "close", "clarify"}:
                existing_ticket = await tickets.get_ticket(ticket_id)
                if existing_ticket is None:
                    await event.message.answer(specialist_texts.NOT_FOUND_TEXT)
                    return
                if not can_change_ticket_status(
                    actor_user_id=actor_id,
                    ticket=existing_ticket,
                    admin_ids=cfg.bot.admin_ids,
                    specialist_ids=cfg.bot.it_specialist_ids,
                ):
                    logger.info(
                        "Status change denied by role: actor=%s ticket_id=%s action=%s",
                        actor_id,
                        ticket_id,
                        action,
                    )
                    await event.message.answer(specialist_texts.FORBIDDEN_TEXT)
                    return

                if action == "release":
                    result = await tickets.release_ticket(
                        ticket_id=ticket_id,
                        actor_user_id=actor_id,
                        admin_ids=cfg.bot.admin_ids,
                    )
                elif action == "close":
                    result = await tickets.close_ticket(
                        ticket_id=ticket_id,
                        actor_user_id=actor_id,
                        actor_name=actor_name,
                        admin_ids=cfg.bot.admin_ids,
                    )
                else:
                    result = await tickets.request_clarification(
                        ticket_id=ticket_id,
                        actor_user_id=actor_id,
                        actor_name=actor_name,
                        admin_ids=cfg.bot.admin_ids,
                    )
            else:
                await event.message.answer("Неизвестное действие.")
                return

            if not result.ok or result.ticket is None:
                logger.warning(
                    "Ticket action failed: actor=%s action=%s ticket_id=%s reason=%s",
                    actor_id,
                    action,
                    ticket_id,
                    result.reason,
                )
                reason_to_text = {
                    "already_assigned": specialist_texts.ALREADY_ASSIGNED_TEXT,
                    "forbidden": specialist_texts.FORBIDDEN_TEXT,
                    "already_closed": specialist_texts.ALREADY_CLOSED_TEXT,
                    "not_assigned": specialist_texts.NOT_ASSIGNED_TEXT,
                }
                await event.message.answer(
                    reason_to_text.get(result.reason, specialist_texts.NOT_FOUND_TEXT)
                )
                return

            logger.info(
                "Ticket action success: actor=%s action=%s ticket_id=%s status=%s",
                actor_id,
                action,
                result.ticket.ticket_id,
                result.ticket.status.value,
            )
            group_mid = ticket_links.get_group_message_id(result.ticket.ticket_id)
            if group_mid:
                await event._ensure_bot().edit_message(
                    message_id=group_mid,
                    text=specialist_texts.render_group_ticket(result.ticket),
                    attachments=[build_ticket_actions_keyboard(result.ticket.ticket_id)],
                )

            await event.message.answer(
                f"Обновлено: {result.ticket.ticket_id} -> {result.ticket.status.value}"
            )
            return

        sender = event.message.sender
        sender_id, _ = get_sender_identity(sender, fallback_name="Пользователь")

        if can_use_network_tools(
            user_id=sender_id,
            admin_ids=cfg.bot.admin_ids,
            specialist_ids=cfg.bot.it_specialist_ids,
        ):
            net_state = network_session.get(sender_id)
            if net_state.step == "awaiting_target":
                return
            if net_state.step == "cooldown":
                network_session.reset(sender_id)
                return

        draft = user_flow.get(sender_id)
        text = normalize_ticket_text(
            raw_text=event.message.body.text,
            empty_text_fallback="",
        )
        if is_command_text(text):
            return

        if draft.step == "awaiting_problem_text":
            if not draft.category:
                user_flow.begin_create(sender_id)
                await event.message.answer(
                    text=user_texts.CATEGORY_PROMPT,
                    attachments=[build_main_menu_keyboard()],
                )
                return

            draft = user_flow.set_problem_text(sender_id, text)
            await event.message.answer(
                text=user_texts.confirm_prompt(
                    draft.category or "Не выбрана",
                    draft.problem_text or "",
                ),
                attachments=[build_confirm_keyboard()],
            )
            return

        if draft.step in {"awaiting_confirmation", "awaiting_category"}:
            await event.message.answer(
                text="Используйте кнопки текущего шага или вернитесь в меню.",
                attachments=[build_main_menu_keyboard()],
            )
            return

        user_flow.begin_create(sender_id)

        if text:
            fallback_category = categories[-1]
            user_flow.set_category(sender_id, fallback_category)
            user_flow.set_problem_text(sender_id, text)
            await event.message.answer(
                text=user_texts.confirm_prompt(fallback_category, text),
                attachments=[build_confirm_keyboard()],
            )
            return

        requester_phone, requester_department = get_optional_contact_details(sender)
        await event.message.answer(
            text=(
                "Выберите категорию обращения кнопкой «Создать обращение».\n"
                f"Профиль: телефон={requester_phone or '-'}, подразделение={requester_department or '-'}"
            ),
            attachments=[build_main_menu_keyboard()],
        )
