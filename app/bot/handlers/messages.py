import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from maxapi.enums.parse_mode import ParseMode
from maxapi.types import BotStarted, MessageCreated

from app.admin.runtime import get_user_access_registry
from app.admin.services.access_service import (
    can_change_ticket_status,
    can_take_ticket,
    can_use_network_tools,
    can_view_service_functions,
    can_view_user_menu,
    is_admin,
)
from app.common.user_helpers import get_first_name, get_full_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_admin_request_keyboard,
    build_main_menu_keyboard,
    build_registration_keyboard,
    build_ticket_actions_keyboard,
)
from app.helpdesk.runtime import (
    get_ticket_link_service,
    get_ticket_service,
    get_user_flow_service,
)
from app.helpdesk.services.ticket_service import (
    get_optional_contact_details,
    get_sender_identity,
    is_command_text,
    normalize_ticket_id,
    normalize_ticket_text,
    parse_specialist_command,
)
from app.helpdesk.texts import specialist_texts, user_texts
from app.network.keyboards.network_keyboards import build_network_menu_keyboard
from app.network.runtime import get_network_session_service, get_network_tools_service
from app.network.texts import network_texts
from config.config import get_config

logger = logging.getLogger(__name__)
_PHONE_PATTERN = re.compile(r"TEL[^:]*:([+0-9\-()\s]+)")
_TICKET_MEDIA_ATTACHMENT_MARKERS = (
    "image",
    "photo",
    "video",
    "file",
    "document",
    "audio",
)
_NON_FORWARDABLE_ATTACHMENT_MARKERS = (
    "contact",
    "inline_keyboard",
    "reply_keyboard",
    "button",
    "sticker",
)


def _resolve_replied_mid(event: MessageCreated) -> str | None:
    linked = event.message.link
    if not linked or not linked.message:
        return None
    return linked.message.mid


def _render_open_tickets(lines: list[str]) -> str:
    if not lines:
        return "Открытых заявок нет."
    return "Открытые заявки:\n" + "\n".join(lines)


def _build_menu_for_user(user_id: int, cfg):
    return _build_menu_for_user_with_registry(
        user_id=user_id,
        cfg=cfg,
        access_registry=get_user_access_registry(),
    )


def _resolve_role_sets(cfg, access_registry):
    admin_ids = set(cfg.bot.admin_ids) | set(access_registry.get_ids_by_role("admin"))
    specialist_ids = set(cfg.bot.it_specialist_ids) | set(
        access_registry.get_ids_by_role("IT specialist")
    )
    user_ids = set(cfg.bot.user_ids) | set(access_registry.get_ids_by_role("user"))
    return tuple(admin_ids), tuple(specialist_ids), tuple(user_ids)


def _build_menu_for_user_with_registry(user_id: int, cfg, access_registry):
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


def _extract_shared_phone(event: MessageCreated) -> str | None:
    attachments = list(getattr(event.message.body, "attachments", None) or [])
    for attachment in attachments:
        att_type = str(getattr(attachment, "type", "")).lower()
        if "contact" not in att_type:
            continue
        payload = getattr(attachment, "payload", None)
        vcf_info = str(getattr(payload, "vcf_info", "") or "")
        if not vcf_info:
            continue
        for line in vcf_info.splitlines():
            match = _PHONE_PATTERN.search(line)
            if match:
                return match.group(1).strip()
    return None


def _extract_ticket_media_attachments(event: MessageCreated) -> list[Any]:
    collected: list[Any] = []
    attachments = list(getattr(event.message.body, "attachments", None) or [])
    for attachment in attachments:
        att_type = str(getattr(attachment, "type", "")).lower()
        if any(marker in att_type for marker in _NON_FORWARDABLE_ATTACHMENT_MARKERS):
            continue
        if any(marker in att_type for marker in _TICKET_MEDIA_ATTACHMENT_MARKERS):
            collected.append(attachment)
    return collected


def register(dp) -> None:
    cfg = get_config()
    tickets = get_ticket_service()
    ticket_links = get_ticket_link_service()
    user_flow = get_user_flow_service()
    network_session = get_network_session_service()
    network_tools = get_network_tools_service()
    access_registry = get_user_access_registry()
    group_chat_id = cfg.bot.group_chat_id
    problem_collect_delay_seconds = 20
    problem_collect_tasks: dict[int, asyncio.Task[None]] = {}

    def _cancel_problem_collect_task(user_id: int) -> None:
        task = problem_collect_tasks.get(user_id)
        if task is None:
            return
        if task is asyncio.current_task():
            return
        problem_collect_tasks.pop(user_id, None)
        if not task.done():
            task.cancel()

    def _get_registered_user_profile(user_id: int) -> tuple[str, str | None]:
        for item in access_registry.list_users():
            if item.user_id == user_id:
                return item.user_name, item.phone
        return f"ID {user_id}", None

    async def _send_delayed_submit(user_id: int, bot) -> None:
        try:
            await asyncio.sleep(problem_collect_delay_seconds)
            draft = user_flow.get(user_id)
            if draft.step not in {
                "awaiting_problem_text",
                "awaiting_wifi_escalation_text",
                "awaiting_tv_escalation_text",
            }:
                logger.info(
                    "Auto-submit skipped by step: user_id=%s step=%s",
                    user_id,
                    draft.step,
                )
                return
            if not draft.category or not draft.problem_text:
                logger.info(
                    "Auto-submit skipped by missing data: user_id=%s category=%s has_text=%s",
                    user_id,
                    draft.category,
                    bool(draft.problem_text),
                )
                return
            requester_name, requester_phone = _get_registered_user_profile(user_id)
            logger.info(
                "Auto-submit started: user_id=%s category=%s has_attachments=%s",
                user_id,
                draft.category,
                bool(draft.attachments),
            )
            await _submit_draft_ticket_by_bot(
                bot=bot,
                sender_id=user_id,
                requester_name=requester_name,
                requester_phone=requester_phone,
                requester_department=None,
            )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Failed to auto-submit delayed draft: user_id=%s", user_id)
        finally:
            current_task = problem_collect_tasks.get(user_id)
            if current_task is asyncio.current_task():
                problem_collect_tasks.pop(user_id, None)

    def _schedule_problem_submit(user_id: int, bot) -> None:
        _cancel_problem_collect_task(user_id)
        logger.info(
            "Auto-submit timer scheduled: user_id=%s delay=%ss",
            user_id,
            problem_collect_delay_seconds,
        )
        problem_collect_tasks[user_id] = asyncio.create_task(
            _send_delayed_submit(user_id, bot)
        )

    async def _notify_admins_about_access_request(
        event: MessageCreated,
        *,
        sender_id: int,
        user_name: str,
        phone: str,
        created_at: str,
        title: str,
    ) -> int:
        admin_buttons = [build_admin_request_keyboard(sender_id)]
        admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        delivered = 0
        for admin_id in admin_ids:
            try:
                await event._ensure_bot().send_message(
                    user_id=admin_id,
                    text=(
                        f"{title}\n"
                        f"ID: {sender_id}\n"
                        f"Имя: {user_name}\n"
                        f"Телефон: {phone}\n"
                        f"Дата: {created_at}"
                    ),
                    attachments=admin_buttons,
                )
                delivered += 1
            except Exception:
                logger.exception(
                    "Failed to deliver access request to admin: requester_id=%s admin_id=%s",
                    sender_id,
                    admin_id,
                )
        if delivered == 0:
            logger.error(
                "Access request notification delivered to 0 admins: requester_id=%s admin_ids=%s",
                sender_id,
                tuple(admin_ids),
            )
        else:
            logger.info(
                "Access request notification delivered: requester_id=%s delivered=%s admins_total=%s",
                sender_id,
                delivered,
                len(tuple(admin_ids)),
            )
        return delivered

    async def _submit_draft_ticket_by_bot(
        *,
        bot,
        sender_id: int,
        requester_name: str,
        requester_phone: str | None,
        requester_department: str | None,
    ) -> bool:
        _cancel_problem_collect_task(sender_id)
        draft = user_flow.get(sender_id)
        if not draft.category or not draft.problem_text:
            return False

        ticket = await tickets.create_ticket(
            requester_user_id=sender_id,
            requester_name=requester_name,
            category=draft.category,
            text=draft.problem_text,
            requester_phone=requester_phone,
            requester_department=requester_department,
        )

        group_sent = None
        ticket_text = specialist_texts.render_group_ticket(ticket)
        action_keyboard = build_ticket_actions_keyboard(ticket.ticket_id)
        media_attachments = list(draft.attachments or [])
        try:
            group_sent = await bot.send_message(
                chat_id=cfg.bot.group_chat_id,
                text=ticket_text,
                attachments=[*media_attachments, action_keyboard],
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception(
                "Message fallback failed with media+actions: ticket_id=%s user_id=%s group_chat_id=%s",
                ticket.ticket_id,
                sender_id,
                cfg.bot.group_chat_id,
            )
            try:
                if media_attachments:
                    group_sent = await bot.send_message(
                        chat_id=cfg.bot.group_chat_id,
                        text=ticket_text,
                        attachments=media_attachments,
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    group_sent = await bot.send_message(
                        chat_id=cfg.bot.group_chat_id,
                        text=ticket_text,
                        attachments=[action_keyboard],
                        parse_mode=ParseMode.HTML,
                    )
            except Exception:
                logger.exception(
                    "Message fallback failed with reduced attachments: ticket_id=%s user_id=%s group_chat_id=%s",
                    ticket.ticket_id,
                    sender_id,
                    cfg.bot.group_chat_id,
                )
                try:
                    group_sent = await bot.send_message(
                        chat_id=cfg.bot.group_chat_id,
                        text=ticket_text,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    logger.exception(
                        "Message fallback failed without attachments: ticket_id=%s user_id=%s group_chat_id=%s",
                        ticket.ticket_id,
                        sender_id,
                        cfg.bot.group_chat_id,
                    )
                    user_flow.reset(sender_id)
                    await bot.send_message(
                        user_id=sender_id,
                        text=(
                            f"Заявка {ticket.ticket_id} сохранена, но не отправлена в группу специалистов.\n"
                            "Проверьте MAX_GROUP_CHAT_ID и права бота в группе."
                        ),
                        attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
                    )
                    return False

        if not group_sent or not getattr(group_sent, "message", None):
            logger.error(
                "Message fallback got empty send response: ticket_id=%s user_id=%s group_chat_id=%s",
                ticket.ticket_id,
                sender_id,
                cfg.bot.group_chat_id,
            )
            user_flow.reset(sender_id)
            await bot.send_message(
                user_id=sender_id,
                text=(
                    f"Заявка {ticket.ticket_id} сохранена, но API не подтвердил отправку в группу.\n"
                    "Проверьте MAX_GROUP_CHAT_ID и доступ бота к чату."
                ),
                attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
            )
            return False

        if group_sent.message and group_sent.message.body:
            ticket_links.bind_group_message(
                ticket_id=ticket.ticket_id,
                group_message_id=group_sent.message.body.mid,
                primary=True,
            )

        user_flow.reset(sender_id)
        user_sent = await bot.send_message(
            user_id=sender_id,
            text=user_texts.SUBMITTED_TEXT,
            attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
        )
        if user_sent and getattr(user_sent, "message", None) and user_sent.message.body:
            ticket_links.bind_user_message(
                ticket_id=ticket.ticket_id,
                user_message_id=user_sent.message.body.mid,
            )
        return True

    async def _submit_draft_ticket(event: MessageCreated, sender_id: int) -> None:
        draft = user_flow.get(sender_id)
        if not draft.category or not draft.problem_text:
            await event.message.answer(
                text="Не хватает данных для отправки. Создайте обращение заново.",
                attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
            )
            return

        sender = event.message.sender
        _, requester_name = get_sender_identity(sender, fallback_name="Пользователь")
        requester_phone, requester_department = get_optional_contact_details(sender)
        await _submit_draft_ticket_by_bot(
            bot=event._ensure_bot(),
            sender_id=sender_id,
            requester_name=requester_name,
            requester_phone=requester_phone,
            requester_department=requester_department,
        )

    async def _relay_group_reply_to_user(
        event: MessageCreated,
        *,
        actor_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any],
    ) -> bool:
        reply_mid = _resolve_replied_mid(event)
        if not reply_mid:
            return False

        ticket_id = ticket_links.get_ticket_id_by_group_message(reply_mid)
        if not ticket_id:
            return False

        ticket = await tickets.get_ticket(ticket_id)
        if ticket is None:
            await event.message.answer(specialist_texts.NOT_FOUND_TEXT)
            return True

        if not text and not attachments:
            return True

        relay_text = (
            f"Ответ по заявке {ticket.ticket_id}\n"
            f"Специалист: {actor_name}\n"
            f"Сообщение:\n{text or '[вложение]'}"
        )
        try:
            if attachments:
                user_sent = await event._ensure_bot().send_message(
                    user_id=ticket.user_id,
                    text=relay_text,
                    attachments=attachments,
                )
            else:
                user_sent = await event._ensure_bot().send_message(
                    user_id=ticket.user_id,
                    text=relay_text,
                )
        except Exception:
            logger.exception(
                "Failed to relay group reply to user: ticket_id=%s actor_id=%s",
                ticket.ticket_id,
                actor_id,
            )
            await event.message.answer("Не удалось доставить сообщение пользователю.")
            return True

        if user_sent and getattr(user_sent, "message", None) and user_sent.message.body:
            ticket_links.bind_user_message(
                ticket_id=ticket.ticket_id,
                user_message_id=user_sent.message.body.mid,
            )

        group_mid = getattr(getattr(event.message, "body", None), "mid", None)
        if group_mid:
            ticket_links.bind_group_message(ticket_id=ticket.ticket_id, group_message_id=group_mid)

        logger.info(
            "Group reply relayed to user: ticket_id=%s actor_id=%s user_id=%s",
            ticket.ticket_id,
            actor_id,
            ticket.user_id,
        )
        return True

    async def _relay_user_reply_to_group(
        event: MessageCreated,
        *,
        sender_id: int,
        sender_name: str,
        text: str,
        attachments: list[Any],
    ) -> bool:
        reply_mid = _resolve_replied_mid(event)
        if not reply_mid:
            return False

        ticket_id = ticket_links.get_ticket_id_by_user_message(reply_mid)
        if not ticket_id:
            return False

        ticket = await tickets.get_ticket(ticket_id)
        if ticket is None:
            await event.message.answer("Не удалось определить заявку для ответа.")
            return True

        if sender_id != ticket.user_id:
            await event.message.answer("Ответ по заявке может отправлять только её автор.")
            return True

        if not text and not attachments:
            return True

        relay_text = (
            f"Сообщение от пользователя по заявке {ticket.ticket_id}\n"
            f"Пользователь: {sender_name}\n"
            f"Сообщение:\n{text or '[вложение]'}"
        )
        try:
            if attachments:
                group_sent = await event._ensure_bot().send_message(
                    chat_id=cfg.bot.group_chat_id,
                    text=relay_text,
                    attachments=attachments,
                )
            else:
                group_sent = await event._ensure_bot().send_message(
                    chat_id=cfg.bot.group_chat_id,
                    text=relay_text,
                )
        except Exception:
            logger.exception(
                "Failed to relay user reply to group: ticket_id=%s user_id=%s",
                ticket.ticket_id,
                sender_id,
            )
            await event.message.answer("Не удалось доставить сообщение в группу поддержки.")
            return True

        if group_sent and getattr(group_sent, "message", None) and group_sent.message.body:
            ticket_links.bind_group_message(
                ticket_id=ticket.ticket_id,
                group_message_id=group_sent.message.body.mid,
            )

        user_mid = getattr(getattr(event.message, "body", None), "mid", None)
        if user_mid:
            ticket_links.bind_user_message(ticket_id=ticket.ticket_id, user_message_id=user_mid)

        logger.info(
            "User reply relayed to group: ticket_id=%s user_id=%s",
            ticket.ticket_id,
            sender_id,
        )
        return True

    async def _submit_access_request(event: MessageCreated, sender_id: int) -> bool:
        phone = _extract_shared_phone(event)
        if not phone:
            await event.message.answer(
                "Для регистрации нажмите кнопку и поделитесь контактом.",
                attachments=[build_registration_keyboard()],
            )
            return False

        user = event.message.sender
        user_name = get_full_name(user, fallback=f"ID {sender_id}")
        status = access_registry.request_access(sender_id, user_name, phone=phone)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if status == "already_approved":
            logger.info("Access request skipped (already_approved): requester_id=%s", sender_id)
            await event.message.answer("Доступ уже одобрен. Используйте /menu.")
            return True
        if status == "already_pending":
            logger.info("Access request repeated (already_pending): requester_id=%s", sender_id)
            delivered = await _notify_admins_about_access_request(
                event,
                sender_id=sender_id,
                user_name=user_name,
                phone=phone,
                created_at=created_at,
                title="Повторная заявка на доступ:",
            )
            if delivered == 0:
                await event.message.answer(
                    "Заявка уже в ожидании, но уведомление администратору не доставлено."
                )
            else:
                await event.message.answer(
                    "Заявка уже отправлена. Я повторно уведомил администратора."
                )
            return True

        logger.info("Access request created: requester_id=%s", sender_id)
        delivered = await _notify_admins_about_access_request(
            event,
            sender_id=sender_id,
            user_name=user_name,
            phone=phone,
            created_at=created_at,
            title="Новая заявка на доступ:",
        )
        if delivered == 0:
            await event.message.answer(
                "Заявка сохранена, но уведомление администратору не доставлено. Проверьте MAX_ADMIN_IDS."
            )
        else:
            await event.message.answer("Заявка на доступ отправлена администратору.")
        return True

    @dp.bot_started()
    async def handle_bot_started(event: BotStarted):
        user = event.user
        name = get_first_name(user, fallback="друг")
        user_id = int(getattr(user, "user_id"))
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(
            user_id,
            cfg,
            approved_user_ids,
            banned_user_ids,
            access_registry,
        ):
            await event.bot.send_message(
                chat_id=event.chat_id,
                text=(
                    "Доступ к боту ограничен.\n"
                    "Нажмите кнопку и поделитесь контактом для регистрации."
                ),
                attachments=[build_registration_keyboard()],
            )
            return

        await event.bot.send_message(
            chat_id=event.chat_id,
            text=(
                f"👋 Привет, {name}!\n\n"
                "Используйте меню, чтобы создать обращение в IT Help Desk."
            ),
            attachments=[_build_menu_for_user_with_registry(user_id, cfg, access_registry)],
        )

    @dp.message_created()
    async def handle_all_messages(event: MessageCreated):
        sender = event.message.sender
        if bool(getattr(sender, "is_bot", False)):
            return

        recipient_chat_id = int(event.message.recipient.chat_id)

        if recipient_chat_id == group_chat_id:
            text = normalize_ticket_text(event.message.body.text, "")
            message_attachments = _extract_ticket_media_attachments(event)

            actor = sender
            actor_id, actor_name = get_sender_identity(actor, fallback_name="Специалист")
            admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)

            if not text.startswith("/"):
                if can_view_service_functions(
                    user_id=actor_id,
                    admin_ids=admin_ids,
                    specialist_ids=specialist_ids,
                ):
                    relayed = await _relay_group_reply_to_user(
                        event,
                        actor_id=actor_id,
                        actor_name=actor_name,
                        text=text,
                        attachments=message_attachments,
                    )
                    if relayed:
                        return
                return

            if text.startswith("/open"):
                if not can_view_service_functions(
                    user_id=actor_id,
                    admin_ids=admin_ids,
                    specialist_ids=specialist_ids,
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
                    admin_ids=admin_ids,
                    specialist_ids=specialist_ids,
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
                    admin_ids=admin_ids,
                    specialist_ids=specialist_ids,
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
                    result = await tickets.request_clarification(
                        ticket_id=ticket_id,
                        actor_user_id=actor_id,
                        actor_name=actor_name,
                        admin_ids=admin_ids,
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
                    parse_mode=ParseMode.HTML,
                )

            await event.message.answer(
                f"Обновлено: {result.ticket.ticket_id} -> {result.ticket.status.value}"
            )
            return

        if recipient_chat_id < 0:
            return

        sender_id, sender_name = get_sender_identity(sender, fallback_name="Пользователь")
        approved_user_ids = access_registry.get_approved_ids()
        banned_user_ids = access_registry.get_banned_ids()
        if not _has_user_access(
            sender_id,
            cfg,
            approved_user_ids,
            banned_user_ids,
            access_registry,
        ):
            await _submit_access_request(event, sender_id)
            return

        text = normalize_ticket_text(
            raw_text=event.message.body.text,
            empty_text_fallback="",
        )
        message_attachments = _extract_ticket_media_attachments(event)

        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        if can_use_network_tools(
            user_id=sender_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            net_state = network_session.get(sender_id)

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
                logger.info("/net command: user_id=%s tool=%s target=%s", sender_id, tool, target)
                result = await network_tools.run_tool(tool, target)
                await event.message.answer(
                    text=network_texts.render_result(result.title, result.ok, result.details),
                    attachments=[build_network_menu_keyboard()],
                )
                return

            if (
                net_state.step == "awaiting_target"
                and net_state.pending_tool
                and text
                and not text.startswith("/")
            ):
                logger.info(
                    "Network target received: user_id=%s tool=%s target=%s",
                    sender_id,
                    net_state.pending_tool,
                    text,
                )
                result = await network_tools.run_tool(net_state.pending_tool, text)
                network_session.mark_processed(sender_id)
                await event.message.answer(
                    text=network_texts.render_result(result.title, result.ok, result.details),
                    attachments=[build_network_menu_keyboard()],
                )
                return

            if net_state.step == "cooldown":
                network_session.reset(sender_id)
                return

        if not is_command_text(text):
            relayed = await _relay_user_reply_to_group(
                event,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                attachments=message_attachments,
            )
            if relayed:
                return

        draft = user_flow.get(sender_id)
        if is_command_text(text):
            return

        is_service_actor = can_view_service_functions(
            user_id=sender_id,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        )

        if draft.step == "awaiting_wifi_escalation_text":
            chunk_text = text if text and not text.startswith("/") else None
            if not chunk_text and not message_attachments:
                return
            draft = user_flow.append_problem_chunk(
                sender_id,
                text=chunk_text,
                attachments=message_attachments,
            )
            draft.step = "awaiting_wifi_escalation_text"
            _schedule_problem_submit(sender_id, event._ensure_bot())
            return

        if draft.step == "awaiting_tv_escalation_text":
            chunk_text = text if text and not text.startswith("/") else None
            if not chunk_text and not message_attachments:
                return
            draft = user_flow.append_problem_chunk(
                sender_id,
                text=chunk_text,
                attachments=message_attachments,
            )
            draft.step = "awaiting_tv_escalation_text"
            _schedule_problem_submit(sender_id, event._ensure_bot())
            return

        if draft.step == "awaiting_problem_text":
            if not draft.category:
                user_flow.begin_create(sender_id)
                await event.message.answer(
                    text=user_texts.CATEGORY_PROMPT,
                    attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
                )
                return

            chunk_text = text if text and not text.startswith("/") else None
            if not chunk_text and not message_attachments:
                return
            draft = user_flow.append_problem_chunk(
                sender_id,
                text=chunk_text,
                attachments=message_attachments,
            )
            draft.step = "awaiting_problem_text"
            _schedule_problem_submit(sender_id, event._ensure_bot())
            return

        if draft.step == "awaiting_confirmation":
            normalized = text.strip().lower()
            if normalized in {"отмена", "cancel", "/cancel"}:
                _cancel_problem_collect_task(sender_id)
                user_flow.reset(sender_id)
                await event.message.answer(
                    text=user_texts.CANCELLED_TEXT,
                    attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
                )
                return
            chunk_text = text if text and not text.startswith("/") else None
            if chunk_text or message_attachments:
                draft = user_flow.append_problem_chunk(
                    sender_id,
                    text=chunk_text,
                    attachments=message_attachments,
                )
                draft.step = "awaiting_problem_text"
                _schedule_problem_submit(sender_id, event._ensure_bot())
            return

        if draft.step == "awaiting_category":
            await event.message.answer(
                text="Используйте кнопки текущего шага или вернитесь в меню.",
                attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
            )
            return

        if draft.step == "idle" and is_service_actor:
            await event.message.answer(
                text="Используйте кнопки меню для действий. Для создания заявки нажмите «Создать обращение».",
                attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
            )
            return

        await event.message.answer(
            text=user_texts.MENU_CATEGORY_HINT_TEXT,
            attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
        )


