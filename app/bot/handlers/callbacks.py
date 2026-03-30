import logging

from maxapi.types import MessageCallback

from app.admin.services.access_service import (
    can_change_ticket_status,
    can_take_ticket,
    can_view_user_menu,
)
from app.common.user_helpers import get_full_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_categories_keyboard,
    build_confirm_keyboard,
    build_main_menu_keyboard,
    build_ticket_actions_keyboard,
)
from app.helpdesk.payloads import SpecialistTicketPayload, UserMenuPayload
from app.helpdesk.runtime import (
    get_ticket_link_service,
    get_ticket_service,
    get_user_flow_service,
)
from app.helpdesk.services.menu_service import get_ticket_categories
from app.helpdesk.texts import specialist_texts, user_texts
from config.config import get_config

logger = logging.getLogger(__name__)


def _build_user_ticket_list_text(lines: list[str]) -> str:
    if not lines:
        return user_texts.NO_TICKETS_TEXT
    return f"{user_texts.MY_TICKETS_HEADER}\n" + "\n".join(lines)


def register(dp) -> None:
    cfg = get_config()
    categories = get_ticket_categories()
    user_flow = get_user_flow_service()
    tickets = get_ticket_service()
    ticket_links = get_ticket_link_service()

    @dp.message_callback(UserMenuPayload.filter())
    async def handle_user_menu_callback(event: MessageCallback, payload: UserMenuPayload):
        user_id = event.callback.user.user_id
        action = payload.action
        if not can_view_user_menu(user_id):
            logger.info("User menu denied for user_id=%s", user_id)
            await event.answer(notification="Доступ ограничен")
            return

        if action == "menu":
            user_flow.reset(user_id)
            await event.message.answer(
                text=user_texts.WELCOME_TEXT,
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Главное меню")
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
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Показал обращения")
            return

        if action == "wifi":
            await event.message.answer(
                text=user_texts.WIFI_HELP_TEXT,
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Инструкция по сети")
            return

        if action == "help":
            await event.message.answer(
                text=user_texts.HELP_TEXT,
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Справка")
            return

        if action == "rewrite":
            draft = user_flow.get(user_id)
            if not draft.category:
                await event.answer(notification="Сначала выберите категорию")
                return

            draft.step = "awaiting_problem_text"
            await event.message.answer(text=user_texts.PROBLEM_PROMPT)
            await event.answer(notification="Введите новый текст")
            return

        if action == "cancel":
            user_flow.reset(user_id)
            await event.message.answer(
                text=user_texts.CANCELLED_TEXT,
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Отменено")
            return

        if action == "confirm_send":
            draft = user_flow.get(user_id)
            if not draft.category or not draft.problem_text:
                await event.answer(notification="Не хватает данных для отправки")
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

            group_sent = await event._ensure_bot().send_message(
                chat_id=cfg.bot.group_chat_id,
                text=specialist_texts.render_group_ticket(ticket),
                attachments=[build_ticket_actions_keyboard(ticket.ticket_id)],
            )

            if group_sent and group_sent.message and group_sent.message.body:
                ticket_links.bind_group_message(
                    ticket_id=ticket.ticket_id,
                    group_message_id=group_sent.message.body.mid,
                )

            user_flow.reset(user_id)
            await event.message.answer(
                text=user_texts.SUBMITTED_TEXT,
                attachments=[build_main_menu_keyboard()],
            )
            await event.answer(notification="Заявка отправлена")
            return

        await event.answer(notification="Неизвестное действие")

    @dp.message_callback(SpecialistTicketPayload.filter())
    async def handle_specialist_ticket_callback(
        event: MessageCallback, payload: SpecialistTicketPayload
    ):
        actor = event.callback.user
        actor_id = actor.user_id
        actor_name = get_full_name(actor, fallback=f"ID {actor_id}")
        action = payload.action
        ticket_id = payload.ticket_id

        if action == "take" and not can_take_ticket(
            user_id=actor_id,
            admin_ids=cfg.bot.admin_ids,
            specialist_ids=cfg.bot.it_specialist_ids,
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
                admin_ids=cfg.bot.admin_ids,
                specialist_ids=cfg.bot.it_specialist_ids,
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
                admin_ids=cfg.bot.admin_ids,
            )
        elif action == "close":
            result = await tickets.close_ticket(
                ticket_id=ticket_id,
                actor_user_id=actor_id,
                actor_name=actor_name,
                admin_ids=cfg.bot.admin_ids,
            )
        elif action == "clarify":
            result = await tickets.request_clarification(
                ticket_id=ticket_id,
                actor_user_id=actor_id,
                actor_name=actor_name,
                admin_ids=cfg.bot.admin_ids,
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
        )
        await event.answer(notification="Статус обновлён")
