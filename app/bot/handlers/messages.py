"""Общие обработчики сообщений MAX и сценарии HelpDesk."""

import asyncio
import logging
import re
from datetime import datetime
from html import escape
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
from app.bot.notifications import notify_user_ticket_closed
from app.bot.services.max_message_service import MaxMessageService
from app.bot.services.media_forward_service import MediaForwardService
from app.common.user_helpers import get_first_name, get_full_name
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_admin_request_keyboard,
    build_attach_user_reply_keyboard,
    build_clarification_cancel_keyboard,
    build_clarification_reply_keyboard,
    build_close_notification_menu_keyboard,
    build_close_reply_cancel_keyboard,
    build_jamaica_cancel_keyboard,
    build_jamaica_issue_categories_keyboard,
    build_jamaica_main_menu_keyboard,
    build_jamaica_room_not_found_keyboard,
    build_knowledge_base_menu_keyboard,
    build_knowledge_cancel_keyboard,
    build_knowledge_scope_keyboard,
    build_knowledge_articles_keyboard,
    build_main_menu_keyboard,
    build_open_tickets_keyboard,
    build_registration_keyboard,
    build_ticket_actions_keyboard,
)
from app.helpdesk.models.media_attachment import (
    MEDIA_OWNER_KNOWLEDGE_ARTICLE,
    MEDIA_OWNER_TICKET_COMMENT,
)
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import TicketStatus
from app.helpdesk.runtime import (
    get_clarification_session_service,
    get_close_reply_session_service,
    get_knowledge_article_create_session_service,
    get_knowledge_base_service,
    get_media_attachment_service,
    get_media_collection_session_service,
    get_ticket_internal_comment_session_service,
    get_ticket_internal_comment_service,
    get_room_ticket_context_service,
    get_ticket_clarification_service,
    get_ticket_link_service,
    get_ticket_service,
    get_user_reply_session_service,
    get_user_flow_service,
)
from app.helpdesk.services.attachment_filter_service import (
    collect_ticket_media_attachments,
    is_audio_attachment,
    summarize_attachment,
)
from app.helpdesk.services.ticket_clarification_service import (
    MAX_CLARIFICATION_MESSAGE_LENGTH,
)
from app.helpdesk.services.ticket_service import (
    get_optional_contact_details,
    get_sender_identity,
    is_command_text,
    normalize_ticket_id,
    normalize_ticket_text,
    parse_specialist_command,
)
from app.helpdesk.services.menu_service import get_ticket_categories
from app.helpdesk.services.ticket_card_update_service import TicketCardUpdateService
from app.helpdesk.services.user_flow_service import UserDraftSourceMessage
from app.helpdesk.texts import knowledge_base_texts, specialist_texts, user_texts
from app.helpdesk.texts.formatters import format_room_context_object
from app.network.keyboards.network_keyboards import (
    build_network_main_menu_keyboard,
    build_network_menu_keyboard,
)
from app.network.runtime import (
    get_netarium_guest_service,
    get_network_session_service,
    get_network_tools_service,
    get_wifi_voucher_service,
)
from app.network.netarium.guest_texts import render_guest_search_result
from app.network.texts import network_texts
from app.network.wifi.voucher_texts import render_voucher_search_result
from app.observability.runtime import get_observability_service
from config.config import get_config

logger = logging.getLogger(__name__)
_PHONE_PATTERN = re.compile(r"TEL[^:]*:([+0-9\-()\s]+)")
_ATTACHMENT_ONLY_PROBLEM_TEXT = "[вложение]"
_AUDIO_ONLY_PROBLEM_TEXT = "[аудиосообщение]"


def _draft_has_problem_content(draft) -> bool:
    """Проверяет, есть ли в черновике текст или пользовательские вложения."""

    return bool(
        draft.problem_text
        or draft.attachments
        or draft.source_audio_messages
    )


def _resolve_draft_problem_text(draft) -> str:
    """Возвращает текст заявки, включая безопасную заглушку для media-only."""

    if draft.problem_text:
        return draft.problem_text
    if draft.source_audio_messages:
        return _AUDIO_ONLY_PROBLEM_TEXT
    return _ATTACHMENT_ONLY_PROBLEM_TEXT


def _message_text_or_media_placeholder(
    text: str,
    audio_source_message: UserDraftSourceMessage | None,
) -> str:
    """Возвращает текст сообщения или понятную media-заглушку."""

    if text:
        return text
    if audio_source_message:
        return _AUDIO_ONLY_PROBLEM_TEXT
    return _ATTACHMENT_ONLY_PROBLEM_TEXT


def _extract_message_id(sent_message) -> str | None:
    """Достаёт MAX message_id из ответа отправки сообщения."""

    body = getattr(getattr(sent_message, "message", None), "body", None)
    mid = getattr(body, "mid", None)
    return str(mid) if mid else None


def _extract_incoming_message_id(event: MessageCreated) -> str | None:
    """Достаёт message_id входящего сообщения без побочных эффектов."""

    body = getattr(event.message, "body", None)
    mid = getattr(body, "mid", None)
    return str(mid) if mid else None


def _resolve_replied_mid(event: MessageCreated) -> str | None:
    """Возвращает ID сообщения, на которое ответил пользователь."""

    linked = event.message.link
    if not linked or not linked.message:
        return None
    return linked.message.mid


def _build_menu_for_user(user_id: int, cfg):
    """Собирает меню пользователя через текущий реестр доступа."""

    return _build_menu_for_user_with_registry(
        user_id=user_id,
        cfg=cfg,
        access_registry=get_user_access_registry(),
    )


def _resolve_role_sets(cfg, access_registry):
    """Объединяет роли из .env и реестра пользователей."""

    admin_ids = set(cfg.bot.admin_ids) | set(access_registry.get_ids_by_role("admin"))
    specialist_ids = set(cfg.bot.it_specialist_ids) | set(
        access_registry.get_ids_by_role("IT specialist")
    )
    user_ids = set(cfg.bot.user_ids) | set(access_registry.get_ids_by_role("user"))
    return tuple(admin_ids), tuple(specialist_ids), tuple(user_ids)


def _build_menu_for_user_with_registry(user_id: int, cfg, access_registry):
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
        can_use_knowledge_base=can_view_service,
    )


def _has_user_access(
    user_id: int,
    cfg,
    approved_user_ids: tuple[int, ...],
    banned_user_ids: tuple[int, ...],
    access_registry,
) -> bool:
    """Проверяет доступ пользователя к диалогу с ботом."""

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
    """Извлекает телефон из contact attachment MAX."""

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


def _extract_ticket_media_attachments(
    event: MessageCreated,
    *,
    include_audio: bool = True,
) -> list[Any]:
    """Отбирает вложения, которые можно переслать в заявку."""

    attachments = list(getattr(event.message.body, "attachments", None) or [])
    media_attachments = collect_ticket_media_attachments(
        attachments,
        include_audio=include_audio,
    )
    if attachments:
        logger.info(
            "Message attachments filtered: incoming=%s accepted=%s",
            [summarize_attachment(attachment) for attachment in attachments],
            [summarize_attachment(attachment) for attachment in media_attachments],
        )
    return media_attachments


def _extract_ticket_audio_source_message(
    event: MessageCreated,
) -> UserDraftSourceMessage | None:
    """Сохраняет исходное audio-сообщение для нативного forward в группу."""

    attachments = list(getattr(event.message.body, "attachments", None) or [])
    audio_attachments = [
        attachment for attachment in attachments if is_audio_attachment(attachment)
    ]
    if not audio_attachments:
        return None
    source_mid = getattr(event.message.body, "mid", None)
    return UserDraftSourceMessage(
        message=event.message,
        message_id=str(source_mid) if source_mid else None,
        attachments=audio_attachments,
    )


def register(dp) -> None:
    """Регистрирует общий обработчик сообщений и сценарии HelpDesk."""

    cfg = get_config()
    tickets = get_ticket_service()
    ticket_links = get_ticket_link_service()
    clarification_sessions = get_clarification_session_service()
    close_reply_sessions = get_close_reply_session_service()
    internal_comment_sessions = get_ticket_internal_comment_session_service()
    internal_comments = get_ticket_internal_comment_service()
    knowledge_article_sessions = get_knowledge_article_create_session_service()
    knowledge_base = get_knowledge_base_service()
    media_attachments = get_media_attachment_service()
    media_collection_sessions = get_media_collection_session_service()
    ticket_clarifications = get_ticket_clarification_service()
    user_reply_sessions = get_user_reply_session_service()
    room_ticket_contexts = get_room_ticket_context_service()
    observability = get_observability_service()
    max_messages = MaxMessageService(observability=observability, retry_config=cfg.max_api)
    media_forward = MediaForwardService()
    ticket_card_updates = TicketCardUpdateService(
        ticket_links=ticket_links,
        group_chat_id=cfg.bot.group_chat_id,
        max_messages=max_messages,
        clarifications=ticket_clarifications,
        internal_comments=internal_comments,
        room_contexts=room_ticket_contexts,
        observability=get_observability_service(),
    )
    user_flow = get_user_flow_service()
    network_session = get_network_session_service()
    network_tools = get_network_tools_service()
    wifi_vouchers = get_wifi_voucher_service()
    netarium_guests = get_netarium_guest_service()
    access_registry = get_user_access_registry()
    group_chat_id = cfg.bot.group_chat_id
    problem_collect_delay_seconds = 20
    problem_collect_tasks: dict[int, asyncio.Task[None]] = {}

    def _cancel_problem_collect_task(user_id: int) -> None:
        """Отменяет отложенную автоотправку черновика заявки."""

        task = problem_collect_tasks.get(user_id)
        if task is None:
            return
        if task is asyncio.current_task():
            return
        problem_collect_tasks.pop(user_id, None)
        if not task.done():
            task.cancel()

    def _get_registered_user_profile(user_id: int) -> tuple[str, str | None]:
        """Возвращает имя и телефон зарегистрированного пользователя."""

        for item in access_registry.list_users():
            if item.user_id == user_id:
                return item.user_name, item.phone
        return f"ID {user_id}", None

    def _save_room_ticket_context(ticket_id: str, draft):
        """Сохраняет контекст номера для карточки заявки."""

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

    def _render_room_context_object_text(room_context: RoomTicketContext | None) -> str | None:
        """Возвращает человекочитаемую строку объекта обслуживания."""

        if room_context is None:
            return None
        return format_room_context_object(
            room_number_snapshot=room_context.room_number_snapshot,
            location_display_snapshot=room_context.location_display_snapshot,
            category_snapshot=room_context.category_snapshot,
        )

    def _kb_root_screen():
        scopes = tuple(knowledge_base.list_scopes())
        return (
            knowledge_base_texts.render_kb_scope_menu(scopes),
            build_knowledge_base_menu_keyboard(scopes),
        )

    def _kb_category_screen(scope_id: int, category_id: int):
        scope = knowledge_base.get_scope(scope_id)
        category = knowledge_base.get_category_by_id(scope_id, category_id)
        if scope is None or category is None:
            return None
        articles = knowledge_base.list_articles_for_category(
            scope_id=scope_id,
            category_id=category_id,
        )
        return (
            knowledge_base_texts.render_kb_category(
                scope_title=scope.title,
                category=category,
                articles=articles,
            ),
            build_knowledge_articles_keyboard(
                scope_id,
                category_id,
                tuple((article.id, article.title) for article in articles[:10]),
            ),
        )

    async def _update_kb_session_prompt(
        *,
        bot,
        sender_id: int,
        text: str,
        keyboard,
    ) -> None:
        """Обновляет текущее KB-сообщение сессии или отправляет fallback."""

        session = knowledge_article_sessions.get(sender_id)
        prompt_message_id = session.prompt_message_id if session else None
        chat_id = session.chat_id if session else None
        if prompt_message_id:
            updated = await max_messages.edit_message(
                bot=bot,
                message_id=prompt_message_id,
                text=text,
                attachments=[keyboard],
                text_format=ParseMode.HTML,
            )
            if updated:
                return
        sent_mid = await max_messages.send_message(
            bot=bot,
            chat_id=chat_id,
            user_id=None if chat_id is not None else sender_id,
            text=text,
            attachments=[keyboard],
            text_format=ParseMode.HTML,
        )
        if sent_mid:
            knowledge_article_sessions.set_prompt_message_id(sender_id, sent_mid)

    def _schedule_media_collection_finalize(actor_id: int) -> None:
        """Запускает или перезапускает task финализации 15-секундного окна."""

        session = media_collection_sessions.get(actor_id)
        if session is None:
            return

        async def _runner(expected_session_id: str) -> None:
            while True:
                current = media_collection_sessions.get(actor_id)
                if current is None or current.session_id != expected_session_id:
                    return
                delay = (current.deadline_at - datetime.now(current.deadline_at.tzinfo)).total_seconds()
                if delay > 0:
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        return
                popped = media_collection_sessions.pop_if_due(actor_id, expected_session_id)
                if popped is None:
                    continue
                await _finalize_media_collection(popped)
                return

        task = asyncio.create_task(_runner(session.session_id))
        media_collection_sessions.set_finalize_task(actor_id, task)

    async def _finalize_media_collection(session) -> None:
        """Сохраняет агрегированный комментарий или KB-заметку после окна тишины."""

        if session.state == "collecting_ticket_comment":
            await _finalize_internal_comment_collection(session)
            return
        if session.state == "collecting_knowledge_article":
            await _finalize_knowledge_article_collection(session)
            return
        if session.state == "collecting_close_reply":
            await _finalize_close_reply_collection(session)
            return

    async def _finalize_internal_comment_collection(session) -> None:
        """Финализирует внутренний комментарий и его media-вложения."""

        ticket = await tickets.get_ticket(session.ticket_key or "")
        if ticket is None:
            return
        room_context = (
            room_ticket_contexts.get_context(ticket.ticket_id)
            if room_ticket_contexts is not None
            else None
        )
        body = session.body_text or "Без текста"
        current_admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
        actor_role = (
            "admin"
            if is_admin(session.actor_user_id, current_admin_ids)
            else "IT specialist"
        )
        try:
            comment = internal_comments.save(
                ticket=ticket,
                actor_user_id=session.actor_user_id,
                actor_name=session.title or "Специалист",
                text=body,
                room_context=room_context,
                actor_role=actor_role,
            )
        except Exception:
            logger.exception(
                "Failed to save internal comment collection: ticket_id=%s actor_id=%s",
                ticket.ticket_id,
                session.actor_user_id,
            )
            return

        if comment.comment_id is not None and session.pending_media:
            try:
                media_attachments.save_many(
                    owner_type=MEDIA_OWNER_TICKET_COMMENT,
                    owner_id=comment.comment_id,
                    ticket_key=ticket.ticket_id,
                    hotel_id=room_context.hotel_id if room_context else None,
                    location_id=room_context.location_id if room_context else None,
                    attachments=session.pending_media,
                    created_by=session.actor_user_id,
                    metadata={"source": "ticket_internal_comment"},
                )
            except Exception:
                # Комментарий уже сохранён: ошибка вложения не должна оставлять
                # в группе его временные сообщения и не должна ломать карточку.
                logger.exception(
                    "Failed to save internal comment media attachments: ticket_id=%s actor_id=%s comment_id=%s",
                    ticket.ticket_id,
                    session.actor_user_id,
                    comment.comment_id,
                )
        await ticket_card_updates.update_group_ticket_card(
            bot=dp.bot,
            ticket=ticket,
            notify=False,
        )
        await _cleanup_internal_comment_messages(
            bot=dp.bot,
            ticket_id=ticket.ticket_id,
            specialist_user_id=session.actor_user_id,
            prompt_message_id=session.prompt_message_id,
            specialist_message_id=None,
            transient_message_ids=session.transient_message_ids,
        )

    async def _finalize_knowledge_article_collection(session) -> None:
        """Финализирует KB-заметку и её media-вложения."""

        article = None
        category_screen = None
        saved_attachment_count = 0
        attachment_save_failed = False
        if session.source_kind == "ticket_note":
            ticket = await tickets.get_ticket(session.ticket_key or "")
            if ticket is None:
                return
            room_context = (
                room_ticket_contexts.get_context(ticket.ticket_id)
                if room_ticket_contexts is not None
                else None
            )
            current_admin_ids, _, _ = _resolve_role_sets(cfg, access_registry)
            actor_role = (
                "admin"
                if is_admin(session.actor_user_id, current_admin_ids)
                else "IT specialist"
            )
            try:
                _, article = knowledge_base.save_ticket_note(
                    ticket=ticket,
                    actor_user_id=session.actor_user_id,
                    actor_name=session.title or "Специалист",
                    title=session.title or "Заметка",
                    text=session.body_text or "Без текста",
                    room_context=room_context,
                    actor_role=actor_role,
                )
            except Exception:
                logger.exception(
                    "Failed to finalize ticket note collection: ticket_id=%s actor_id=%s",
                    ticket.ticket_id,
                    session.actor_user_id,
                )
                await max_messages.send_message(
                    bot=dp.bot,
                    chat_id=session.chat_id,
                    text="Не удалось сохранить заметку в базу знаний. Попробуйте ещё раз.",
                    text_format=None,
                )
                return
            logger.info(
                "Ticket note knowledge article saved: ticket_id=%s actor_id=%s article_id=%s pending_media=%s",
                ticket.ticket_id,
                session.actor_user_id,
                article.id,
                len(session.pending_media),
            )
            if article is not None and session.pending_media:
                try:
                    saved_items = media_attachments.save_many(
                        owner_type=MEDIA_OWNER_KNOWLEDGE_ARTICLE,
                        owner_id=article.id,
                        ticket_key=ticket.ticket_id,
                        hotel_id=room_context.hotel_id if room_context else None,
                        location_id=room_context.location_id if room_context else None,
                        attachments=session.pending_media,
                        created_by=session.actor_user_id,
                        metadata={"source": "ticket_note"},
                    )
                    saved_attachment_count = len(saved_items)
                except Exception:
                    attachment_save_failed = True
                    logger.exception(
                        "Failed to save ticket note media attachments: ticket_id=%s actor_id=%s article_id=%s",
                        ticket.ticket_id,
                        session.actor_user_id,
                        article.id,
                    )
            await ticket_card_updates.update_group_ticket_card(
                bot=dp.bot,
                ticket=ticket,
                notify=False,
            )
            save_text = (
                f"{knowledge_base_texts.COMMENT_SAVE_NOTIFICATION}\n"
                f"<b>{escape(article.title if article else (session.title or 'Заметка'))}</b>\n\n"
                f"Вложения: {saved_attachment_count}."
            )
            if attachment_save_failed:
                save_text += "\n\nЧасть вложений сохранить не удалось."
            await max_messages.send_message(
                bot=dp.bot,
                chat_id=session.chat_id,
                text=save_text,
                text_format=ParseMode.HTML,
            )
        else:
            try:
                article = knowledge_base.create_manual_article(
                    scope_id=session.scope_id,
                    hotel_id=session.hotel_id,
                    category_id=session.category_id,
                    title=session.title or "Заметка",
                    body=session.body_text or "Без текста",
                    author_user_id=session.actor_user_id,
                )
            except Exception:
                logger.exception(
                    "Failed to finalize manual KB collection: actor_id=%s scope_id=%s category_id=%s",
                    session.actor_user_id,
                    session.scope_id,
                    session.category_id,
                )
                return
            if session.pending_media:
                try:
                    saved_items = media_attachments.save_many(
                        owner_type=MEDIA_OWNER_KNOWLEDGE_ARTICLE,
                        owner_id=article.id,
                        ticket_key=None,
                        hotel_id=session.hotel_id,
                        location_id=session.location_id,
                        attachments=session.pending_media,
                        created_by=session.actor_user_id,
                        metadata={"source": "manual_knowledge_article"},
                    )
                    saved_attachment_count = len(saved_items)
                except Exception:
                    attachment_save_failed = True
                    logger.exception(
                        "Failed to save manual KB media attachments: actor_id=%s article_id=%s scope_id=%s category_id=%s",
                        session.actor_user_id,
                        article.id,
                        session.scope_id,
                        session.category_id,
                    )
            await max_messages.send_message(
                bot=dp.bot,
                user_id=session.actor_user_id,
                text=knowledge_base_texts.render_manual_article_saved_with_attachments(
                    session.scope_title or "Раздел",
                    session.category_title or "Без категории",
                    article.title,
                    saved_attachment_count,
                ),
                text_format=ParseMode.HTML,
            )
            if attachment_save_failed:
                await max_messages.send_message(
                    bot=dp.bot,
                    user_id=session.actor_user_id,
                    text="Часть вложений сохранить не удалось.",
                    text_format=None,
                )
            if session.scope_id and session.category_id:
                category_screen = _kb_category_screen(session.scope_id, session.category_id)
        if session.prompt_message_id:
            try:
                await max_messages.delete_message(bot=dp.bot, message_id=session.prompt_message_id)
            except Exception:
                logger.exception(
                    "Failed to delete KB media collection prompt: actor_id=%s prompt_message_id=%s",
                    session.actor_user_id,
                    session.prompt_message_id,
                )
        if category_screen is not None:
            category_text, category_keyboard = category_screen
            await max_messages.send_message(
                bot=dp.bot,
                user_id=session.actor_user_id,
                text=category_text,
                attachments=[category_keyboard],
                text_format=ParseMode.HTML,
            )

    async def _start_internal_comment_collection(
        event: MessageCreated,
        *,
        actor_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any],
    ) -> bool:
        """Запускает или продолжает 15-секундный сбор внутреннего комментария."""

        session = internal_comment_sessions.get(actor_id)
        if session is None:
            return False
        if is_command_text(text):
            return False
        collected = media_attachments.collect_supported(0, attachments)
        incoming_message_id = _extract_incoming_message_id(event)
        if not text.strip() and not collected.accepted:
            await event.message.answer("Отправьте текст, фото, видео или файл.")
            return True
        media_session = media_collection_sessions.start(
            actor_user_id=actor_id,
            chat_id=group_chat_id,
            state="collecting_ticket_comment",
            ticket_key=session.ticket_id,
            hotel_id=session.hotel_id,
            category_id=session.category_id,
            category_title=session.category_title,
            location_id=session.location_id,
            location_display=session.location_display,
            title=actor_name,
            prompt_message_id=session.prompt_message_id,
            source_kind="internal_comment",
            transient_message_ids=[incoming_message_id] if incoming_message_id else None,
        )
        media_collection_sessions.append(
            actor_id,
            text=text,
            media=collected.accepted,
            warnings=collected.rejected_messages,
            transient_message_ids=[incoming_message_id] if incoming_message_id else None,
        )
        internal_comment_sessions.finish(actor_id)
        _schedule_media_collection_finalize(actor_id)
        for warning in collected.rejected_messages:
            await event.message.answer(warning)
        return True

    async def _save_ticket_note(
        event: MessageCreated,
        *,
        actor_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any],
    ) -> bool:
        """Сохраняет KB-заметку специалиста по заявке из групповой карточки."""

        session = knowledge_article_sessions.get(actor_id)
        if session is None or session.source_kind != "ticket_note":
            return False

        if is_command_text(text):
            return False

        if session.step == "waiting_title":
            if not text:
                await _update_kb_session_prompt(
                    bot=event._ensure_bot(),
                    sender_id=actor_id,
                    text="Введите тему заметки текстом.",
                    keyboard=build_knowledge_cancel_keyboard(),
                )
                return True
            title = text.strip()
            if len(title) > 120:
                await _update_kb_session_prompt(
                    bot=event._ensure_bot(),
                    sender_id=actor_id,
                    text="Тема должна быть не длиннее 120 символов.",
                    keyboard=build_knowledge_cancel_keyboard(),
                )
                return True
            knowledge_article_sessions.set_title(actor_id, title)

            # MAX передаёт подпись к фото или видео как текст сообщения. Если
            # специалист ввёл тему вместе с вложениями, не теряем их на шаге
            # ввода темы: сразу открываем общее 15-секундное окно сбора.
            collected = media_attachments.collect_supported(0, attachments)
            if collected.accepted:
                media_collection_sessions.start(
                    actor_user_id=actor_id,
                    chat_id=session.chat_id or group_chat_id,
                    state="collecting_knowledge_article",
                    ticket_key=session.ticket_id,
                    scope_id=session.scope_id,
                    scope_title=session.scope_title,
                    hotel_id=session.hotel_id,
                    category_id=session.category_id,
                    category_title=session.category_title,
                    title=title,
                    prompt_message_id=session.prompt_message_id,
                    source_kind=session.source_kind,
                )
                media_collection_sessions.append(
                    actor_id,
                    media=collected.accepted,
                    warnings=collected.rejected_messages,
                )
                knowledge_article_sessions.finish(actor_id)
                await max_messages.edit_message(
                    bot=event._ensure_bot(),
                    message_id=session.prompt_message_id,
                    text=knowledge_base_texts.render_media_collection_prompt(title=title),
                    attachments=[build_knowledge_cancel_keyboard()],
                    text_format=ParseMode.HTML,
                )
                logger.info(
                    "Ticket note media collection started from title: ticket_id=%s actor_id=%s title=%r attachments=%s",
                    session.ticket_id,
                    actor_id,
                    title,
                    len(collected.accepted),
                )
                _schedule_media_collection_finalize(actor_id)
                for warning in collected.rejected_messages:
                    await event.message.answer(warning)
                return True

            await _update_kb_session_prompt(
                bot=event._ensure_bot(),
                sender_id=actor_id,
                text=knowledge_base_texts.render_comment_body_prompt(
                    ticket_id=session.ticket_id or "заявка",
                    title=title,
                ),
                keyboard=build_knowledge_cancel_keyboard(),
            )
            return True

        if session.step != "waiting_body":
            return False

        collected = media_attachments.collect_supported(0, attachments)
        if not text and not collected.accepted:
            await _update_kb_session_prompt(
                bot=event._ensure_bot(),
                sender_id=actor_id,
                text="Отправьте текст, фото, видео или файл.",
                keyboard=build_knowledge_cancel_keyboard(),
            )
            return True
        body = text.strip()
        if len(body) > 4000:
            await _update_kb_session_prompt(
                bot=event._ensure_bot(),
                sender_id=actor_id,
                text="Текст заметки должен быть не длиннее 4000 символов.",
                keyboard=build_knowledge_cancel_keyboard(),
            )
            return True

        media_collection_sessions.start(
            actor_user_id=actor_id,
            chat_id=session.chat_id or group_chat_id,
            state="collecting_knowledge_article",
            ticket_key=session.ticket_id,
            scope_id=session.scope_id,
            scope_title=session.scope_title,
            hotel_id=session.hotel_id,
            category_id=session.category_id,
            category_title=session.category_title,
            title=session.title,
            prompt_message_id=session.prompt_message_id,
            source_kind=session.source_kind,
        )
        media_collection_sessions.append(
            actor_id,
            text=body,
            media=collected.accepted,
            warnings=collected.rejected_messages,
        )
        knowledge_article_sessions.finish(actor_id)
        logger.info(
            "Ticket note media collection started: ticket_id=%s actor_id=%s title=%r attachments=%s",
            session.ticket_id,
            actor_id,
            session.title,
            len(collected.accepted),
        )
        await max_messages.edit_message(
            bot=event._ensure_bot(),
            message_id=session.prompt_message_id,
            text=knowledge_base_texts.render_media_collection_prompt(title=session.title),
            attachments=[build_knowledge_cancel_keyboard()],
            text_format=ParseMode.HTML,
        )
        _schedule_media_collection_finalize(actor_id)
        for warning in collected.rejected_messages:
            await event.message.answer(warning)
        return True

    async def _send_delayed_submit(user_id: int, bot) -> None:
        """Автоматически отправляет черновик после паузы в сообщениях."""

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
            if not draft.category or not _draft_has_problem_content(draft):
                logger.info(
                    "Auto-submit skipped by missing data: user_id=%s category=%s "
                    "has_text=%s has_attachments=%s has_audio=%s",
                    user_id,
                    draft.category,
                    bool(draft.problem_text),
                    bool(draft.attachments),
                    bool(draft.source_audio_messages),
                )
                return
            requester_name, requester_phone = _get_registered_user_profile(user_id)
            logger.info(
                "Auto-submit started: user_id=%s category=%s has_attachments=%s has_audio=%s",
                user_id,
                draft.category,
                bool(draft.attachments),
                bool(draft.source_audio_messages),
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
        """Перезапускает таймер автоотправки черновика."""

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
        """Уведомляет администраторов о новой заявке на доступ."""

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
        """Создает заявку из черновика и отправляет карточку в IT-группу."""

        _cancel_problem_collect_task(sender_id)
        draft = user_flow.get(sender_id)
        if not draft.category or not _draft_has_problem_content(draft):
            return False

        ticket = await tickets.create_ticket(
            requester_user_id=sender_id,
            requester_name=requester_name,
            category=draft.category,
            text=_resolve_draft_problem_text(draft),
            requester_phone=requester_phone,
            requester_department=requester_department,
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
            group_sent = await bot.send_message(
                chat_id=cfg.bot.group_chat_id,
                text=ticket_text,
                attachments=[*media_attachments, action_keyboard],
                format=ParseMode.HTML,
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
                        format=ParseMode.HTML,
                    )
                else:
                    group_sent = await bot.send_message(
                        chat_id=cfg.bot.group_chat_id,
                        text=ticket_text,
                        attachments=[action_keyboard],
                        format=ParseMode.HTML,
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
                        format=ParseMode.HTML,
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
            group_message_id = str(group_sent.message.body.mid)
            ticket_links.bind_group_message(
                ticket_id=ticket.ticket_id,
                group_message_id=group_message_id,
                primary=True,
            )
            await observability.ticket_event(
                ticket_id=ticket.ticket_id,
                event_type="message_relayed_to_group",
                actor_user_id=sender_id,
                actor_name=requester_name,
                actor_role="user",
                source="user_message",
                related_message_id=group_message_id,
                metadata={"message_kind": "ticket_card"},
            )
            if media_attachments:
                await observability.ticket_event(
                    ticket_id=ticket.ticket_id,
                    event_type="attachment_received",
                    actor_user_id=sender_id,
                    actor_name=requester_name,
                    actor_role="user",
                    source="user_message",
                    related_message_id=group_message_id,
                    metadata={"count": len(media_attachments)},
                )
            forwarded_audio_mids = await media_forward.forward_audio_messages(
                bot=bot,
                source_messages=list(draft.source_audio_messages or []),
                ticket_id=ticket.ticket_id,
                user_id=sender_id,
                target_chat_id=cfg.bot.group_chat_id,
            )
            for forwarded_mid in forwarded_audio_mids:
                ticket_links.bind_group_message(
                    ticket_id=ticket.ticket_id,
                    group_message_id=forwarded_mid,
                    primary=False,
                )
            ticket_clarifications.set_ticket_base_attachments(
                ticket_id=ticket.ticket_id,
                attachments=media_attachments,
            )

        user_flow.reset(sender_id)
        confirmation_mid = await max_messages.send_message(
            bot=bot,
            user_id=sender_id,
            text=user_texts.SUBMITTED_TEXT,
            text_format=None,
        )
        menu_sent = await bot.send_message(
            user_id=sender_id,
            text=user_texts.WELCOME_TEXT,
            attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
        )
        menu_mid = _extract_message_id(menu_sent)
        user_message_id = confirmation_mid or menu_mid
        if user_message_id:
            ticket_links.bind_user_message(
                ticket_id=ticket.ticket_id,
                user_message_id=user_message_id,
            )
        return True

    async def _submit_draft_ticket(event: MessageCreated, sender_id: int) -> None:
        draft = user_flow.get(sender_id)
        if not draft.category or not _draft_has_problem_content(draft):
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
        audio_source_message: UserDraftSourceMessage | None = None,
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

        if not text and not attachments and not audio_source_message:
            return True

        relay_text = (
            f"Ответ по заявке {ticket.ticket_id}\n"
            f"Специалист: {actor_name}\n"
            f"Сообщение:\n{_message_text_or_media_placeholder(text, audio_source_message)}"
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
        if audio_source_message:
            forwarded_audio_mids = await media_forward.forward_audio_messages(
                bot=event._ensure_bot(),
                source_messages=[audio_source_message],
                ticket_id=ticket.ticket_id,
                user_id=actor_id,
                target_user_id=ticket.user_id,
            )
            for forwarded_mid in forwarded_audio_mids:
                ticket_links.bind_user_message(
                    ticket_id=ticket.ticket_id,
                    user_message_id=forwarded_mid,
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

    async def _cleanup_clarification_messages(
        *,
        bot,
        ticket_id: str,
        specialist_user_id: int,
        prompt_message_id: str | None,
        specialist_message_id: str | None,
    ) -> None:
        """Удаляет временные сообщения сценария уточнения."""

        prompt_deleted = await max_messages.delete_message(
            bot=bot,
            message_id=prompt_message_id,
        )
        specialist_deleted = await max_messages.delete_message(
            bot=bot,
            message_id=specialist_message_id,
        )
        if prompt_deleted:
            logger.info(
                "Clarification prompt message deleted: ticket_id=%s specialist_user_id=%s "
                "prompt_message_id=%s",
                ticket_id,
                specialist_user_id,
                prompt_message_id,
            )
        else:
            logger.warning(
                "Failed to delete clarification prompt message: ticket_id=%s "
                "specialist_user_id=%s prompt_message_id=%s",
                ticket_id,
                specialist_user_id,
                prompt_message_id,
            )
        if specialist_deleted:
            logger.info(
                "Clarification specialist message deleted: ticket_id=%s "
                "specialist_user_id=%s specialist_message_id=%s",
                ticket_id,
                specialist_user_id,
                specialist_message_id,
            )
        else:
            logger.warning(
                "Failed to delete clarification specialist message: ticket_id=%s "
                "specialist_user_id=%s specialist_message_id=%s",
                ticket_id,
                specialist_user_id,
                specialist_message_id,
            )

    async def _cleanup_close_reply_messages(
        *,
        bot,
        ticket_id: str,
        specialist_user_id: int,
        prompt_message_id: str | None,
        specialist_message_id: str | None,
        transient_message_ids: list[str] | None = None,
    ) -> None:
        """Удаляет временные сообщения сценария закрытия с ответом."""

        message_ids = [message_id for message_id in (prompt_message_id, specialist_message_id) if message_id]
        for message_id in transient_message_ids or []:
            if message_id and message_id not in message_ids:
                message_ids.append(message_id)
        async def _delete_pass(*, retry: bool) -> None:
            for message_id in message_ids:
                deleted = await max_messages.delete_message(bot=bot, message_id=message_id)
                if deleted:
                    logger.info(
                        "Close-reply transient message delete requested: ticket_id=%s "
                        "specialist_user_id=%s message_id=%s retry=%s",
                        ticket_id,
                        specialist_user_id,
                        message_id,
                        retry,
                    )
                else:
                    logger.warning(
                        "Failed to delete close-reply transient message: ticket_id=%s "
                        "specialist_user_id=%s message_id=%s retry=%s",
                        ticket_id,
                        specialist_user_id,
                        message_id,
                        retry,
                    )

        await _delete_pass(retry=False)
        # MAX может ещё обрабатывать media-сообщение в момент первой попытки.
        # Повтор не влияет на основную карточку и остаётся best-effort.
        if message_ids:
            await asyncio.sleep(2)
            await _delete_pass(retry=True)

    async def _finalize_close_reply_collection(session) -> None:
        """Доставляет пользователю собранный ответ, затем закрывает заявку."""

        ticket = await tickets.get_ticket(session.ticket_key or "")
        if ticket is None:
            return
        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        if not can_change_ticket_status(
            actor_user_id=session.actor_user_id,
            ticket=ticket,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ) or ticket.status == TicketStatus.CLOSED:
            return

        reply_text = session.body_text or "Смотрите вложения."
        user_message_text = user_texts.render_ticket_closed_with_reply_notification(
            ticket,
            reply_text,
        )
        user_sent_mid = await max_messages.send_message(
            bot=dp.bot,
            user_id=ticket.user_id,
            text=user_message_text,
            attachments=[*session.pending_media, build_close_notification_menu_keyboard()],
            text_format=None,
        )
        if not user_sent_mid:
            logger.warning(
                "Close-with-reply collection delivery failed, ticket not closed: ticket_id=%s actor_id=%s",
                ticket.ticket_id,
                session.actor_user_id,
            )
            await max_messages.send_message(
                bot=dp.bot,
                chat_id=session.chat_id,
                text="Не удалось отправить сообщение пользователю. Заявка не закрыта.",
                text_format=None,
            )
            return

        ticket_links.bind_user_message(ticket_id=ticket.ticket_id, user_message_id=user_sent_mid)
        actor_role = "admin" if is_admin(session.actor_user_id, admin_ids) else "IT specialist"
        ticket_clarifications.save_closing_reply(
            ticket_id=ticket.ticket_id,
            actor_user_id=session.actor_user_id,
            actor_name=session.title or "Специалист",
            text=reply_text,
            attachments=session.pending_media,
            source_message_id=session.transient_message_ids[0] if session.transient_message_ids else None,
            target_message_id=user_sent_mid,
            actor_role=actor_role,
        )
        await observability.ticket_event(
            ticket_id=ticket.ticket_id,
            event_type="ticket_close_reply_sent_to_user",
            actor_user_id=session.actor_user_id,
            actor_name=session.title or "Специалист",
            actor_role=actor_role,
            source="group_media_collection",
            related_message_id=user_sent_mid,
            metadata={"attachments_count": len(session.pending_media)},
        )
        result = await tickets.close_ticket(
            ticket_id=ticket.ticket_id,
            actor_user_id=session.actor_user_id,
            actor_name=session.title or "Специалист",
            admin_ids=admin_ids,
        )
        if not result.ok or result.ticket is None:
            await max_messages.send_message(
                bot=dp.bot,
                chat_id=session.chat_id,
                text="Ответ пользователю отправлен, но заявку не удалось закрыть.",
                text_format=None,
            )
            return

        await ticket_card_updates.update_group_ticket_card(bot=dp.bot, ticket=result.ticket, notify=False)
        await _cleanup_close_reply_messages(
            bot=dp.bot,
            ticket_id=result.ticket.ticket_id,
            specialist_user_id=session.actor_user_id,
            prompt_message_id=session.prompt_message_id,
            specialist_message_id=None,
            transient_message_ids=session.transient_message_ids,
        )
        logger.info(
            "Ticket closed with collected reply: ticket_id=%s actor_id=%s user_message_id=%s attachments=%s",
            result.ticket.ticket_id,
            session.actor_user_id,
            user_sent_mid,
            len(session.pending_media),
        )

    async def _cleanup_internal_comment_messages(
        *,
        bot,
        ticket_id: str,
        specialist_user_id: int,
        prompt_message_id: str | None,
        specialist_message_id: str | None,
        transient_message_ids: list[str] | None = None,
    ) -> None:
        """Удаляет временные сообщения сценария внутреннего комментария."""

        message_ids: list[str] = []
        if prompt_message_id:
            message_ids.append(prompt_message_id)
        if specialist_message_id:
            message_ids.append(specialist_message_id)
        for message_id in transient_message_ids or []:
            if message_id and message_id not in message_ids:
                message_ids.append(message_id)

        for message_id in message_ids:
            deleted = await max_messages.delete_message(
                bot=bot,
                message_id=message_id,
            )
            if not deleted:
                logger.warning(
                    "Internal comment cleanup delete failed: ticket_id=%s specialist_user_id=%s message_id=%s",
                    ticket_id,
                    specialist_user_id,
                    message_id,
                )
            else:
                logger.info(
                    "Internal comment transient message deleted: ticket_id=%s specialist_user_id=%s message_id=%s",
                    ticket_id,
                    specialist_user_id,
                    message_id,
                )

    async def _send_close_reply_to_user(
        event: MessageCreated,
        *,
        actor_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any],
    ) -> bool:
        """Запускает сбор ответа и вложений для закрытия заявки."""

        session = close_reply_sessions.get(actor_id)
        if session is None:
            return False

        bot = event._ensure_bot()
        specialist_message_id = getattr(getattr(event.message, "body", None), "mid", None)
        specialist_message_id = str(specialist_message_id) if specialist_message_id else None

        if text == "/cancel":
            close_reply_sessions.cancel(actor_id)
            await observability.ticket_event(
                ticket_id=session.ticket_id,
                event_type="ticket_close_reply_cancelled",
                actor_user_id=actor_id,
                actor_name=actor_name,
                actor_role="IT specialist",
                source="group_command",
            )
            await _cleanup_close_reply_messages(
                bot=bot,
                ticket_id=session.ticket_id,
                specialist_user_id=actor_id,
                prompt_message_id=session.prompt_message_id,
                specialist_message_id=specialist_message_id,
            )
            return True

        if is_command_text(text):
            return False

        ticket = await tickets.get_ticket(session.ticket_id)
        if ticket is None:
            close_reply_sessions.reset(actor_id)
            await event.message.answer(specialist_texts.NOT_FOUND_TEXT)
            return True

        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        if not can_change_ticket_status(
            actor_user_id=actor_id,
            ticket=ticket,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            close_reply_sessions.reset(actor_id)
            await event.message.answer(specialist_texts.FORBIDDEN_TEXT)
            return True

        if ticket.status == TicketStatus.CLOSED:
            close_reply_sessions.reset(actor_id)
            await event.message.answer(specialist_texts.ALREADY_CLOSED_TEXT)
            return True

        collected = media_attachments.collect_supported(0, attachments)
        if not text.strip() and not collected.accepted:
            await event.message.answer("Отправьте текст, фото, видео или файл.")
            return True

        incoming_message_id = _extract_incoming_message_id(event)
        media_collection_sessions.start(
            actor_user_id=actor_id,
            chat_id=session.group_chat_id or group_chat_id,
            state="collecting_close_reply",
            ticket_key=ticket.ticket_id,
            title=actor_name,
            prompt_message_id=session.prompt_message_id,
            source_kind="close_reply",
            transient_message_ids=[incoming_message_id] if incoming_message_id else None,
        )
        media_collection_sessions.append(
            actor_id,
            text=text,
            media=collected.accepted,
            warnings=collected.rejected_messages,
            transient_message_ids=[incoming_message_id] if incoming_message_id else None,
        )
        close_reply_sessions.finish(actor_id)
        await max_messages.edit_message(
            bot=bot,
            message_id=session.prompt_message_id,
            text=(
                "Можно приложить фото, видео или файл.\n"
                "Всё, что придёт в течение 15 секунд после последнего сообщения, "
                "будет отправлено пользователю вместе с ответом."
            ),
            attachments=[build_close_reply_cancel_keyboard(ticket.ticket_id)],
            text_format=None,
        )
        _schedule_media_collection_finalize(actor_id)
        for warning in collected.rejected_messages:
            await event.message.answer(warning)
        logger.info(
            "Close-with-reply media collection started: ticket_id=%s actor_id=%s attachments=%s",
            ticket.ticket_id,
            actor_id,
            len(collected.accepted),
        )
        return True

    async def _send_clarification_question_to_user(
        event: MessageCreated,
        *,
        actor_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any],
        audio_source_message: UserDraftSourceMessage | None = None,
    ) -> bool:
        """Отправляет введённый специалистом вопрос автору заявки."""

        session = clarification_sessions.get(actor_id)
        if session is None:
            return False

        bot = event._ensure_bot()
        specialist_message_id = getattr(getattr(event.message, "body", None), "mid", None)
        specialist_message_id = str(specialist_message_id) if specialist_message_id else None

        if text == "/cancel":
            clarification_sessions.reset(actor_id)
            await _cleanup_clarification_messages(
                bot=bot,
                ticket_id=session.ticket_id,
                specialist_user_id=actor_id,
                prompt_message_id=session.prompt_message_id,
                specialist_message_id=specialist_message_id,
            )
            logger.info(
                "Clarification canceled by legacy command: ticket_id=%s "
                "specialist_user_id=%s prompt_message_id=%s specialist_message_id=%s",
                session.ticket_id,
                actor_id,
                session.prompt_message_id,
                specialist_message_id,
            )
            return True

        if is_command_text(text):
            return False

        if not text and not attachments and not audio_source_message:
            await event.message.answer(
                "Введите текст вопроса для пользователя."
            )
            return True

        if text and len(text) > MAX_CLARIFICATION_MESSAGE_LENGTH:
            await event.message.answer(
                "Текст уточнения слишком длинный. Сократите его до "
                f"{MAX_CLARIFICATION_MESSAGE_LENGTH} символов."
            )
            return True

        ticket = await tickets.get_ticket(session.ticket_id)
        if ticket is None:
            clarification_sessions.reset(actor_id)
            await event.message.answer(specialist_texts.NOT_FOUND_TEXT)
            return True

        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        if not can_change_ticket_status(
            actor_user_id=actor_id,
            ticket=ticket,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            clarification_sessions.reset(actor_id)
            await event.message.answer(specialist_texts.FORBIDDEN_TEXT)
            return True

        question_text = (
            f"Уточнение по заявке {ticket.ticket_id}\n"
            f"Специалист: {actor_name}\n"
            f"Вопрос:\n{_message_text_or_media_placeholder(text, audio_source_message)}"
        )
        user_attachments = [
            *attachments,
            build_clarification_reply_keyboard(ticket.ticket_id),
        ]
        try:
            user_sent = await bot.send_message(
                user_id=ticket.user_id,
                text=question_text,
                attachments=user_attachments,
            )
        except Exception:
            logger.exception(
                "Failed to send clarification question: ticket_id=%s actor_id=%s",
                ticket.ticket_id,
                actor_id,
            )
            await event.message.answer("Не удалось доставить вопрос пользователю.")
            return True

        result = await tickets.request_clarification(
            ticket_id=ticket.ticket_id,
            actor_user_id=actor_id,
            actor_name=actor_name,
            admin_ids=admin_ids,
        )
        if not result.ok or result.ticket is None:
            clarification_sessions.reset(actor_id)
            await event.message.answer(specialist_texts.NOT_FOUND_TEXT)
            return True

        if user_sent and getattr(user_sent, "message", None) and user_sent.message.body:
            user_sent_mid = str(user_sent.message.body.mid)
            ticket_links.bind_user_message(
                ticket_id=result.ticket.ticket_id,
                user_message_id=user_sent_mid,
            )
        else:
            user_sent_mid = None
        if audio_source_message:
            forwarded_audio_mids = await media_forward.forward_audio_messages(
                bot=bot,
                source_messages=[audio_source_message],
                ticket_id=result.ticket.ticket_id,
                user_id=actor_id,
                target_user_id=result.ticket.user_id,
            )
            for forwarded_mid in forwarded_audio_mids:
                ticket_links.bind_user_message(
                    ticket_id=result.ticket.ticket_id,
                    user_message_id=forwarded_mid,
                )

        ticket_clarifications.save_last(
            ticket_id=result.ticket.ticket_id,
            actor_user_id=actor_id,
            actor_name=actor_name,
            text=_message_text_or_media_placeholder(text, audio_source_message),
            attachments=attachments,
            source_message_id=specialist_message_id,
            target_message_id=user_sent_mid,
        )
        await observability.ticket_event(
            ticket_id=result.ticket.ticket_id,
            event_type="clarification_sent_to_user",
            actor_user_id=actor_id,
            actor_name=actor_name,
            actor_role="IT specialist",
            source="user_message",
            related_message_id=user_sent_mid,
            metadata={"has_attachments": bool(attachments or audio_source_message)},
        )
        await observability.ticket_event(
            ticket_id=result.ticket.ticket_id,
            event_type="message_relayed_to_user",
            actor_user_id=actor_id,
            actor_name=actor_name,
            actor_role="IT specialist",
            source="user_message",
            related_message_id=user_sent_mid,
            metadata={"message_kind": "clarification"},
        )
        clarification_sessions.reset(actor_id)
        card_updated = await ticket_card_updates.update_group_ticket_card(
            bot=bot,
            ticket=result.ticket,
            notify=False,
        )
        if card_updated:
            logger.info(
                "Ticket card updated with clarification: ticket_id=%s specialist_user_id=%s",
                result.ticket.ticket_id,
                actor_id,
            )
        else:
            logger.warning(
                "Failed to update ticket card with clarification: ticket_id=%s "
                "specialist_user_id=%s",
                result.ticket.ticket_id,
                actor_id,
            )
        await _cleanup_clarification_messages(
            bot=bot,
            ticket_id=result.ticket.ticket_id,
            specialist_user_id=actor_id,
            prompt_message_id=session.prompt_message_id,
            specialist_message_id=specialist_message_id,
        )
        logger.info(
            "Clarification question sent: ticket_id=%s actor_id=%s user_id=%s "
            "prompt_message_id=%s specialist_message_id=%s",
            result.ticket.ticket_id,
            actor_id,
            result.ticket.user_id,
            session.prompt_message_id,
            specialist_message_id,
        )
        return True

    async def _save_internal_comment(
        event: MessageCreated,
        *,
        actor_id: int,
        actor_name: str,
        text: str,
        attachments: list[Any],
    ) -> bool:
        """Переключает ввод внутреннего комментария в 15-секундный режим сбора."""

        session = internal_comment_sessions.get(actor_id)
        if session is None:
            return False

        bot = event._ensure_bot()
        specialist_message_id = getattr(getattr(event.message, "body", None), "mid", None)
        specialist_message_id = str(specialist_message_id) if specialist_message_id else None

        if text == "/cancel":
            internal_comment_sessions.cancel(actor_id)
            await _cleanup_internal_comment_messages(
                bot=bot,
                ticket_id=session.ticket_id,
                specialist_user_id=actor_id,
                prompt_message_id=session.prompt_message_id,
                specialist_message_id=specialist_message_id,
            )
            return True

        if is_command_text(text):
            return False

        ticket = await tickets.get_ticket(session.ticket_id)
        if ticket is None:
            internal_comment_sessions.cancel(actor_id)
            await event.message.answer(specialist_texts.NOT_FOUND_TEXT)
            return True

        admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)
        if not can_change_ticket_status(
            actor_user_id=actor_id,
            ticket=ticket,
            admin_ids=admin_ids,
            specialist_ids=specialist_ids,
        ):
            internal_comment_sessions.cancel(actor_id)
            await event.message.answer(specialist_texts.FORBIDDEN_TEXT)
            return True

        if len(text.strip()) > 4000:
            await event.message.answer("Комментарий должен быть не длиннее 4000 символов.")
            return True

        return await _start_internal_comment_collection(
            event,
            actor_id=actor_id,
            actor_name=actor_name,
            text=text,
            attachments=attachments,
        )

    async def _collect_active_media_session(
        event: MessageCreated,
        *,
        actor_id: int,
        text: str,
        attachments: list[Any],
    ) -> bool:
        """Добавляет сообщение в активное 15-секундное окно сбора."""

        session = media_collection_sessions.get(actor_id)
        if session is None:
            return False
        current_chat_id = int(event.message.recipient.chat_id)
        if session.chat_id != current_chat_id:
            return False
        if is_command_text(text):
            return False
        existing_count = len(session.pending_media)
        collected = media_attachments.collect_supported(existing_count, attachments)
        if not text.strip() and not collected.accepted and not collected.rejected_messages:
            return True
        incoming_message_id = _extract_incoming_message_id(event)
        media_collection_sessions.append(
            actor_id,
            text=text,
            media=collected.accepted,
            warnings=collected.rejected_messages,
            transient_message_ids=[incoming_message_id] if incoming_message_id else None,
        )
        _schedule_media_collection_finalize(actor_id)
        for warning in collected.rejected_messages:
            await event.message.answer(warning)
        return True

    async def _relay_user_reply_to_group(
        event: MessageCreated,
        *,
        sender_id: int,
        sender_name: str,
        text: str,
        attachments: list[Any],
        audio_source_message: UserDraftSourceMessage | None = None,
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

        if not text and not attachments and not audio_source_message:
            return True

        relay_text = (
            f"Сообщение от пользователя по заявке {ticket.ticket_id}\n"
            f"Пользователь: {sender_name}\n"
            f"Сообщение:\n{_message_text_or_media_placeholder(text, audio_source_message)}"
        )
        user_mid = getattr(getattr(event.message, "body", None), "mid", None)
        user_mid = str(user_mid) if user_mid else None

        try:
            if attachments:
                group_sent = await event._ensure_bot().send_message(
                    chat_id=cfg.bot.group_chat_id,
                    text=relay_text,
                    attachments=[
                        *attachments,
                        build_attach_user_reply_keyboard(ticket.ticket_id),
                    ],
                )
            else:
                group_sent = await event._ensure_bot().send_message(
                    chat_id=cfg.bot.group_chat_id,
                    text=relay_text,
                    attachments=[build_attach_user_reply_keyboard(ticket.ticket_id)],
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
            group_mid = group_sent.message.body.mid
            ticket_links.bind_group_message(
                ticket_id=ticket.ticket_id,
                group_message_id=group_mid,
            )
            ticket_clarifications.save_user_reply_candidate(
                ticket_id=ticket.ticket_id,
                user_id=sender_id,
                user_name=sender_name,
                text=_message_text_or_media_placeholder(text, audio_source_message),
                group_message_id=group_mid,
                attachments=attachments,
                source_message_id=user_mid,
            )
            await observability.ticket_event(
                ticket_id=ticket.ticket_id,
                event_type="user_reply_received",
                actor_user_id=sender_id,
                actor_name=sender_name,
                actor_role="user",
                source="user_message",
                related_message_id=str(group_mid),
                metadata={"has_attachments": bool(attachments or audio_source_message)},
            )
            await observability.ticket_event(
                ticket_id=ticket.ticket_id,
                event_type="message_relayed_to_group",
                actor_user_id=sender_id,
                actor_name=sender_name,
                actor_role="user",
                source="user_message",
                related_message_id=str(group_mid),
                metadata={"message_kind": "user_reply"},
            )
            if audio_source_message:
                forwarded_audio_mids = await media_forward.forward_audio_messages(
                    bot=event._ensure_bot(),
                    source_messages=[audio_source_message],
                    ticket_id=ticket.ticket_id,
                    user_id=sender_id,
                    target_chat_id=cfg.bot.group_chat_id,
                )
                for forwarded_mid in forwarded_audio_mids:
                    ticket_links.bind_group_message(
                        ticket_id=ticket.ticket_id,
                        group_message_id=forwarded_mid,
                    )

        if user_mid:
            ticket_links.bind_user_message(ticket_id=ticket.ticket_id, user_message_id=user_mid)

        logger.info(
            "User reply relayed to group: ticket_id=%s user_id=%s",
            ticket.ticket_id,
            sender_id,
        )
        return True

    async def _send_pending_user_reply_to_group(
        event: MessageCreated,
        *,
        sender_id: int,
        sender_name: str,
        text: str,
        attachments: list[Any],
        audio_source_message: UserDraftSourceMessage | None = None,
    ) -> bool:
        """Отправляет ответ пользователя из режима ожидания по кнопке."""

        session = user_reply_sessions.get(sender_id)
        if session is None:
            return False

        if text == "/cancel":
            user_reply_sessions.reset(sender_id)
            await event.message.answer("Ответ по заявке отменён.")
            logger.info(
                "User reply session canceled: ticket_id=%s user_id=%s",
                session.ticket_id,
                sender_id,
            )
            return True

        if is_command_text(text):
            return False

        if not text and not attachments and not audio_source_message:
            await event.message.answer("Введите текст ответа или добавьте вложение.")
            return True

        ticket = await tickets.get_ticket(session.ticket_id)
        if ticket is None:
            user_reply_sessions.reset(sender_id)
            await event.message.answer("Не удалось определить заявку для ответа.")
            return True

        if sender_id != ticket.user_id:
            user_reply_sessions.reset(sender_id)
            await event.message.answer("Ответ по заявке может отправлять только её автор.")
            return True

        relay_text = (
            f"Сообщение от пользователя по заявке {ticket.ticket_id}\n"
            f"Пользователь: {sender_name}\n"
            f"Сообщение:\n{_message_text_or_media_placeholder(text, audio_source_message)}"
        )
        user_mid = getattr(getattr(event.message, "body", None), "mid", None)
        user_mid = str(user_mid) if user_mid else None

        group_message_id = ticket_links.get_group_message_id(ticket.ticket_id)
        group_sent_mid = await max_messages.send_message(
            bot=event._ensure_bot(),
            chat_id=cfg.bot.group_chat_id,
            text=relay_text,
            attachments=[
                *attachments,
                build_attach_user_reply_keyboard(ticket.ticket_id),
            ],
            reply_to_message_id=group_message_id,
            text_format=None,
            notify=False,
        )
        if not group_sent_mid:
            await event.message.answer("Не удалось доставить сообщение в группу поддержки.")
            logger.warning(
                "Pending user reply delivery failed: ticket_id=%s user_id=%s",
                ticket.ticket_id,
                sender_id,
            )
            return True

        ticket_links.bind_group_message(
            ticket_id=ticket.ticket_id,
            group_message_id=group_sent_mid,
        )
        ticket_clarifications.save_user_reply_candidate(
            ticket_id=ticket.ticket_id,
            user_id=sender_id,
            user_name=sender_name,
            text=_message_text_or_media_placeholder(text, audio_source_message),
            group_message_id=group_sent_mid,
            attachments=attachments,
            source_message_id=user_mid,
        )
        await observability.ticket_event(
            ticket_id=ticket.ticket_id,
            event_type="user_reply_received",
            actor_user_id=sender_id,
            actor_name=sender_name,
            actor_role="user",
            source="user_message",
            related_message_id=group_sent_mid,
            metadata={"has_attachments": bool(attachments or audio_source_message)},
        )
        await observability.ticket_event(
            ticket_id=ticket.ticket_id,
            event_type="message_relayed_to_group",
            actor_user_id=sender_id,
            actor_name=sender_name,
            actor_role="user",
            source="user_message",
            related_message_id=group_sent_mid,
            metadata={"message_kind": "user_reply"},
        )
        if audio_source_message:
            forwarded_audio_mids = await media_forward.forward_audio_messages(
                bot=event._ensure_bot(),
                source_messages=[audio_source_message],
                ticket_id=ticket.ticket_id,
                user_id=sender_id,
                target_chat_id=cfg.bot.group_chat_id,
            )
            for forwarded_mid in forwarded_audio_mids:
                ticket_links.bind_group_message(
                    ticket_id=ticket.ticket_id,
                    group_message_id=forwarded_mid,
                )
        if user_mid:
            ticket_links.bind_user_message(
                ticket_id=ticket.ticket_id,
                user_message_id=user_mid,
            )

        user_reply_sessions.reset(sender_id)
        await event.message.answer(f"Ответ по заявке {ticket.ticket_id} отправлен.")
        logger.info(
            "Pending user reply relayed to group: ticket_id=%s user_id=%s group_mid=%s",
            ticket.ticket_id,
            sender_id,
            group_sent_mid,
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
            await observability.audit(
                action="access_requested",
                resource_type="user",
                resource_id=str(sender_id),
                result="denied",
                actor_user_id=sender_id,
                actor_role="user",
                reason="already_approved",
            )
            await event.message.answer("Доступ уже одобрен. Используйте /menu.")
            return True
        if status == "already_pending":
            logger.info("Access request repeated (already_pending): requester_id=%s", sender_id)
            await observability.audit(
                action="access_requested",
                resource_type="user",
                resource_id=str(sender_id),
                result="success",
                actor_user_id=sender_id,
                actor_role="user",
                reason="already_pending",
                metadata={"notification_repeated": True},
            )
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
        await observability.audit(
            action="access_requested",
            resource_type="user",
            resource_id=str(sender_id),
            result="success",
            actor_user_id=sender_id,
            actor_role="user",
            metadata={"has_phone": bool(phone)},
        )
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
                f"Привет, {name}!\n\n"
                "Меню IT Help Desk\n\n"
                "Выберите нужное действие в меню."
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
            audio_source_message = _extract_ticket_audio_source_message(event)
            relay_message_attachments = (
                _extract_ticket_media_attachments(event, include_audio=False)
                if audio_source_message
                else message_attachments
            )

            actor = sender
            actor_id, actor_name = get_sender_identity(actor, fallback_name="Специалист")
            admin_ids, specialist_ids, _ = _resolve_role_sets(cfg, access_registry)

            media_collected = await _collect_active_media_session(
                event,
                actor_id=actor_id,
                text=text,
                attachments=message_attachments,
            )
            if media_collected:
                return

            close_reply_sent = await _send_close_reply_to_user(
                event,
                actor_id=actor_id,
                actor_name=actor_name,
                text=text,
                attachments=relay_message_attachments,
            )
            if close_reply_sent:
                return

            clarification_sent = await _send_clarification_question_to_user(
                event,
                actor_id=actor_id,
                actor_name=actor_name,
                text=text,
                attachments=relay_message_attachments,
                audio_source_message=audio_source_message,
            )
            if clarification_sent:
                return

            internal_comment_saved = await _save_internal_comment(
                event,
                actor_id=actor_id,
                actor_name=actor_name,
                text=text,
                attachments=message_attachments,
            )
            if internal_comment_saved:
                return

            ticket_note_saved = await _save_ticket_note(
                event,
                actor_id=actor_id,
                actor_name=actor_name,
                text=text,
                attachments=message_attachments,
            )
            if ticket_note_saved:
                return

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
                        attachments=relay_message_attachments,
                        audio_source_message=audio_source_message,
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
                attachments = [build_open_tickets_keyboard(open_tickets)] if open_tickets else None
                await event.message.answer(
                    specialist_texts.render_open_tickets_list(
                        open_tickets,
                        title="Открытые заявки",
                    ),
                    attachments=attachments,
                    format=ParseMode.HTML,
                )
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
            elif action in {"release", "close", "clarify", "close_with_reply"}:
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

                if action == "clarify":
                    active_session = clarification_sessions.get_by_ticket(existing_ticket.ticket_id)
                    if active_session and active_session.actor_user_id != actor_id:
                        await event.message.answer(
                            "Уточнение уже начал другой специалист."
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
                        ticket_id=existing_ticket.ticket_id,
                        group_chat_id=group_chat_id,
                    )
                    prompt_sent = await event.message.answer(
                        "Введите вопрос для пользователя по заявке "
                        f"{existing_ticket.ticket_id} следующим сообщением "
                        "в этом чате.",
                        attachments=[
                            build_clarification_cancel_keyboard(existing_ticket.ticket_id)
                        ],
                    )
                    prompt_message_id = _extract_message_id(prompt_sent)
                    clarification_sessions.set_prompt_message_id(actor_id, prompt_message_id)
                    logger.info(
                        "Clarification session started: ticket_id=%s specialist_user_id=%s "
                        "prompt_message_id=%s session_id=%s",
                        existing_ticket.ticket_id,
                        actor_id,
                        prompt_message_id,
                        session.session_id,
                    )
                    return

                if action == "close_with_reply":
                    if existing_ticket.status == TicketStatus.CLOSED:
                        await event.message.answer(specialist_texts.ALREADY_CLOSED_TEXT)
                        return
                    active_session = close_reply_sessions.get_by_ticket(existing_ticket.ticket_id)
                    if active_session and active_session.actor_user_id != actor_id:
                        await event.message.answer(
                            "Закрытие с ответом уже начал другой специалист."
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
                        ticket_id=existing_ticket.ticket_id,
                        group_chat_id=group_chat_id,
                    )
                    prompt_message_id = await max_messages.send_message(
                        bot=event._ensure_bot(),
                        chat_id=group_chat_id,
                        text="Введите сообщение пользователю о выполненной работе.",
                        attachments=[
                            build_close_reply_cancel_keyboard(existing_ticket.ticket_id)
                        ],
                        text_format=None,
                    )
                    if not prompt_message_id:
                        close_reply_sessions.cancel(actor_id)
                        await event.message.answer(
                            "Не удалось отправить запрос ответа. Попробуйте ещё раз."
                        )
                        return
                    close_reply_sessions.set_prompt_message_id(actor_id, prompt_message_id)
                    await observability.ticket_event(
                        ticket_id=existing_ticket.ticket_id,
                        event_type="ticket_close_reply_started",
                        actor_user_id=actor_id,
                        actor_name=actor_name,
                        actor_role="IT specialist",
                        source="group_command",
                    )
                    logger.info(
                        "Close-with-reply session started by command: ticket_id=%s "
                        "specialist_user_id=%s prompt_message_id=%s session_id=%s",
                        existing_ticket.ticket_id,
                        actor_id,
                        prompt_message_id,
                        session.session_id,
                    )
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
            await ticket_card_updates.update_group_ticket_card(
                bot=event._ensure_bot(),
                ticket=result.ticket,
                notify=False,
            )

            if action == "close":
                await notify_user_ticket_closed(event._ensure_bot(), result.ticket)

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
        audio_source_message = _extract_ticket_audio_source_message(event)
        draft_message_attachments = (
            _extract_ticket_media_attachments(event, include_audio=False)
            if audio_source_message
            else message_attachments
        )
        draft_audio_sources = [audio_source_message] if audio_source_message else None

        if text in {"/start", "/menu"}:
            user_flow.reset(sender_id)
            network_session.reset(sender_id)
            user_reply_sessions.reset(sender_id)
            knowledge_article_sessions.reset(sender_id)
            await event.message.answer(
                text=user_texts.WELCOME_TEXT,
                attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
            )
            logger.info(
                "Main menu command handled by fallback message handler: user_id=%s command=%s",
                sender_id,
                text,
            )
            return

        media_collected = await _collect_active_media_session(
            event,
            actor_id=sender_id,
            text=text,
            attachments=message_attachments,
        )
        if media_collected:
            return

        kb_session = knowledge_article_sessions.get(sender_id)
        if kb_session is not None:
            if text == "/cancel":
                knowledge_article_sessions.reset(sender_id)
                kb_root_text, kb_root_keyboard = _kb_root_screen()
                await _update_kb_session_prompt(
                    bot=event._ensure_bot(),
                    sender_id=sender_id,
                    text=kb_root_text,
                    keyboard=kb_root_keyboard,
                )
                return
            if message_attachments or audio_source_message:
                if kb_session.step != "waiting_body":
                    await _update_kb_session_prompt(
                        bot=event._ensure_bot(),
                        sender_id=sender_id,
                        text="На этом шаге принимается только текст.\n\n[Отмена]",
                        keyboard=build_knowledge_cancel_keyboard(),
                    )
                    return
            if kb_session.step == "waiting_title":
                if not text:
                    await _update_kb_session_prompt(
                        bot=event._ensure_bot(),
                        sender_id=sender_id,
                        text="Введите тему заметки текстом.",
                        keyboard=build_knowledge_cancel_keyboard(),
                    )
                    return
                title = text.strip()
                if len(title) > 120:
                    await _update_kb_session_prompt(
                        bot=event._ensure_bot(),
                        sender_id=sender_id,
                        text="Тема должна быть не длиннее 120 символов.",
                        keyboard=build_knowledge_cancel_keyboard(),
                    )
                    return
                knowledge_article_sessions.set_title(sender_id, title)
                await _update_kb_session_prompt(
                    bot=event._ensure_bot(),
                    sender_id=sender_id,
                    text=knowledge_base_texts.render_manual_article_body_prompt(
                        kb_session.scope_title or "Раздел",
                        kb_session.category_title or "Без категории",
                        title,
                    ),
                    keyboard=build_knowledge_cancel_keyboard(),
                )
                return
            if kb_session.step == "waiting_body":
                collected = media_attachments.collect_supported(0, message_attachments)
                if not text and not collected.accepted:
                    await _update_kb_session_prompt(
                        bot=event._ensure_bot(),
                        sender_id=sender_id,
                        text="Отправьте текст, фото, видео или файл.",
                        keyboard=build_knowledge_cancel_keyboard(),
                    )
                    return
                body = text.strip()
                if len(body) > 4000:
                    await _update_kb_session_prompt(
                        bot=event._ensure_bot(),
                        sender_id=sender_id,
                        text="Текст заметки должен быть не длиннее 4000 символов.",
                        keyboard=build_knowledge_cancel_keyboard(),
                    )
                    return
                media_collection_sessions.start(
                    actor_user_id=sender_id,
                    chat_id=recipient_chat_id,
                    state="collecting_knowledge_article",
                    scope_id=kb_session.scope_id,
                    scope_title=kb_session.scope_title,
                    hotel_id=kb_session.hotel_id,
                    category_id=kb_session.category_id,
                    category_title=kb_session.category_title,
                    title=kb_session.title,
                    prompt_message_id=kb_session.prompt_message_id,
                    source_kind="manual",
                )
                media_collection_sessions.append(
                    sender_id,
                    text=body,
                    media=collected.accepted,
                    warnings=collected.rejected_messages,
                )
                await _update_kb_session_prompt(
                    bot=event._ensure_bot(),
                    sender_id=sender_id,
                    text=knowledge_base_texts.render_media_collection_prompt(title=kb_session.title),
                    keyboard=build_knowledge_cancel_keyboard(),
                )
                knowledge_article_sessions.finish(sender_id)
                _schedule_media_collection_finalize(sender_id)
                for warning in collected.rejected_messages:
                    await event.message.answer(warning)
                return

        pending_reply_sent = await _send_pending_user_reply_to_group(
            event,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            attachments=draft_message_attachments,
            audio_source_message=audio_source_message,
        )
        if pending_reply_sent:
            return

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
                result = await network_tools.run_tool(
                    tool,
                    target,
                    actor_user_id=sender_id,
                    actor_name=sender_name,
                )
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
                if net_state.pending_tool == "wifi_voucher":
                    logger.info("WiFi voucher room received: user_id=%s room=%s", sender_id, text)
                    # Сначала проверяем номер в Netarium, чтобы не запускать
                    # долгий поиск по страницам WiFi.link для несуществующей комнаты.
                    guest_result = await netarium_guests.find_by_room(
                        text,
                        actor_user_id=sender_id,
                        actor_name=sender_name,
                        chat_type=event.message.recipient.chat_type,
                    )
                    if not guest_result.ok:
                        await event.message.answer(
                            text=render_guest_search_result(guest_result),
                            attachments=[build_network_main_menu_keyboard()],
                            format=ParseMode.HTML,
                        )
                        return
                    if not guest_result.room_exists:
                        await event.message.answer(
                            text="Такого номера не существует",
                            attachments=[build_network_main_menu_keyboard()],
                        )
                        return

                    # WiFi-сценарий остается активным после ответа: следующий
                    # текст пользователя снова считается номером комнаты.
                    result = await wifi_vouchers.find_first_by_room(
                        text,
                        actor_user_id=sender_id,
                        actor_name=sender_name,
                        chat_type=event.message.recipient.chat_type,
                        room_exists_in_netarium=guest_result.room_exists,
                        guest_found_in_netarium=guest_result.stay is not None,
                    )
                    await event.message.answer(
                        text=render_voucher_search_result(result),
                        format=ParseMode.HTML,
                    )
                    await event.message.answer(
                        text=render_guest_search_result(guest_result),
                        attachments=[build_network_main_menu_keyboard()],
                        format=ParseMode.HTML,
                    )
                    return

                logger.info(
                    "Network target received: user_id=%s tool=%s target=%s",
                    sender_id,
                    net_state.pending_tool,
                    text,
                )
                result = await network_tools.run_tool(
                    net_state.pending_tool,
                    text,
                    actor_user_id=sender_id,
                    actor_name=sender_name,
                )
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
                attachments=draft_message_attachments,
                audio_source_message=audio_source_message,
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
                attachments=draft_message_attachments,
                source_audio_messages=draft_audio_sources,
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
                attachments=draft_message_attachments,
                source_audio_messages=draft_audio_sources,
            )
            draft.step = "awaiting_tv_escalation_text"
            _schedule_problem_submit(sender_id, event._ensure_bot())
            return

        if draft.step == "awaiting_room_number":
            if room_ticket_contexts is None or not draft.hotel_id:
                user_flow.reset(sender_id)
                await event.message.answer(
                    text="Справочник номеров недоступен. Вернитесь в главное меню.",
                    attachments=[_build_menu_for_user_with_registry(sender_id, cfg, access_registry)],
                )
                return
            room_number = text.strip()
            if not room_number or room_number.startswith("/"):
                await event.message.answer(
                    text="Введите номер комнаты или домика текстом.",
                    attachments=[build_jamaica_room_not_found_keyboard()],
                )
                return
            location = room_ticket_contexts.find_location(draft.hotel_id, room_number)
            if location is None:
                await event.message.answer(
                    text="Такого номера не существует.",
                    attachments=[build_jamaica_room_not_found_keyboard()],
                )
                return
            categories_for_room = room_ticket_contexts.list_location_categories(
                draft.hotel_id,
            )
            if not categories_for_room:
                user_flow.reset(sender_id)
                await event.message.answer(
                    text="Для этого отеля не настроены категории заявок.",
                    attachments=[build_jamaica_cancel_keyboard()],
                )
                return
            user_flow.set_room_ticket_location(
                sender_id,
                location_id=location.id,
                room_number=location.room_number,
                location_display=location.display_name,
            )
            await event.message.answer(
                text=(
                    f"Объект: {location.display_name}\n"
                    "Выберите категорию обращения."
                ),
                attachments=[build_jamaica_issue_categories_keyboard(categories_for_room)],
            )
            return

        if draft.step == "awaiting_problem_text":
            if not draft.category:
                user_flow.begin_create(sender_id)
                await event.message.answer(
                    text=user_texts.CATEGORY_PROMPT,
                    attachments=[build_categories_keyboard(get_ticket_categories())],
                )
                return

            chunk_text = text if text and not text.startswith("/") else None
            if not chunk_text and not message_attachments:
                return
            draft = user_flow.append_problem_chunk(
                sender_id,
                text=chunk_text,
                attachments=draft_message_attachments,
                source_audio_messages=draft_audio_sources,
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
                    attachments=draft_message_attachments,
                    source_audio_messages=draft_audio_sources,
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
