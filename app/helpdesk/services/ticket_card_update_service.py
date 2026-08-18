"""Обновление групповой карточки заявки в MAX."""

import logging
from typing import Any

from maxapi.enums.parse_mode import ParseMode

from app.bot.services.max_message_service import MaxMessageService
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_ticket_actions_keyboard,
    build_user_ticket_keyboard,
)
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.services.ticket_internal_comment_service import TicketInternalCommentService
from app.helpdesk.services.postgres_ticket_link_service import PostgresTicketLinkService
from app.helpdesk.services.ticket_clarification_service import TicketClarificationService
from app.helpdesk.services.ticket_link_service import TicketLinkService
from app.helpdesk.services.ticket_user_addition_service import TicketUserAdditionService
from app.helpdesk.texts import specialist_texts, user_texts
from app.observability.services import ObservabilityService


logger = logging.getLogger(__name__)


class TicketCardUpdateService:
    """Обновляет основную карточку заявки."""

    def __init__(
        self,
        *,
        ticket_links: TicketLinkService | PostgresTicketLinkService,
        group_chat_id: int,
        max_messages: MaxMessageService | None = None,
        clarifications: TicketClarificationService | None = None,
        internal_comments: TicketInternalCommentService | None = None,
        user_additions: TicketUserAdditionService | None = None,
        room_contexts=None,
        observability: ObservabilityService | None = None,
    ) -> None:
        self._ticket_links = ticket_links
        self._group_chat_id = group_chat_id
        self._max_messages = max_messages or MaxMessageService()
        self._clarifications = clarifications
        self._internal_comments = internal_comments
        self._user_additions = user_additions
        self._room_contexts = room_contexts
        self._observability = observability

    async def update_group_ticket_card(
        self,
        *,
        bot,
        ticket: Ticket,
        notify: bool = False,
    ) -> bool:
        """Обновляет карточку на месте."""

        ticket_id = ticket.ticket_id
        group_message_id = self._ticket_links.get_group_message_id(ticket_id)
        text = specialist_texts.render_group_ticket(
            ticket,
            room_context=self._get_room_context(ticket_id),
            last_clarification=self._get_last_clarification(ticket_id),
            attached_user_reply=self._get_attached_user_reply(ticket_id),
            closing_reply=self._get_closing_reply(ticket_id),
            last_internal_comment=self._get_last_internal_comment(ticket_id),
            last_user_addition=self._get_last_user_addition(ticket_id),
        )
        room_context = self._get_room_context(ticket_id)
        keyboard = build_ticket_actions_keyboard(ticket, room_context=room_context)
        attachments = self._build_card_attachments(ticket_id, keyboard)

        if group_message_id:
            updated = await self._max_messages.edit_message(
                bot=bot,
                message_id=group_message_id,
                text=text,
                attachments=attachments,
                text_format=ParseMode.HTML,
                notify=notify,
            )
            if updated:
                await self._sync_user_ticket_card(bot=bot, ticket=ticket)
                logger.info(
                    "Ticket card updated in-place: ticket_id=%s message_id=%s status=%s",
                    ticket_id,
                    group_message_id,
                    ticket.status.value,
                )
                await self._record_card_event(
                    ticket_id=ticket_id,
                    event_type="ticket_card_updated",
                    related_message_id=group_message_id,
                    metadata={"mode": "edit"},
                )
                return True

            logger.warning(
                "Ticket card in-place update failed, sending reply fallback: "
                "ticket_id=%s message_id=%s",
                ticket_id,
                group_message_id,
            )
            fallback_mid = await self._max_messages.send_message(
                bot=bot,
                chat_id=self._group_chat_id,
                text=text,
                attachments=attachments,
                reply_to_message_id=group_message_id,
                text_format=ParseMode.HTML,
                notify=notify,
            )
            if fallback_mid:
                self._ticket_links.bind_group_message(
                    ticket_id=ticket_id,
                    group_message_id=fallback_mid,
                    primary=True,
                )
                await self._sync_user_ticket_card(bot=bot, ticket=ticket)
                logger.info(
                    "Ticket card fallback sent as new primary: ticket_id=%s message_id=%s",
                    ticket_id,
                    fallback_mid,
                )
                await self._record_card_event(
                    ticket_id=ticket_id,
                    event_type="ticket_card_updated",
                    related_message_id=fallback_mid,
                    metadata={"mode": "fallback_reply"},
                )
                return True

            logger.error(
                "Ticket card fallback failed: ticket_id=%s original_message_id=%s",
                ticket_id,
                group_message_id,
            )
            await self._record_card_event(
                ticket_id=ticket_id,
                event_type="ticket_card_update_failed",
                related_message_id=group_message_id,
                metadata={"mode": "fallback_reply"},
            )
            return False

        logger.warning(
            "Ticket card primary link missing, sending new card: ticket_id=%s",
            ticket_id,
        )
        new_mid = await self._max_messages.send_message(
            bot=bot,
            chat_id=self._group_chat_id,
            text=text,
            attachments=attachments,
            text_format=ParseMode.HTML,
            notify=notify,
        )
        if new_mid:
            self._ticket_links.bind_group_message(
                ticket_id=ticket_id,
                group_message_id=new_mid,
                primary=True,
            )
            await self._sync_user_ticket_card(bot=bot, ticket=ticket)
            logger.info(
                "Ticket card sent without previous link: ticket_id=%s message_id=%s",
                ticket_id,
                new_mid,
            )
            await self._record_card_event(
                ticket_id=ticket_id,
                event_type="ticket_card_updated",
                related_message_id=new_mid,
                metadata={"mode": "new_primary"},
            )
            return True

        logger.error("Ticket card update failed without fallback: ticket_id=%s", ticket_id)
        await self._record_card_event(
            ticket_id=ticket_id,
            event_type="ticket_card_update_failed",
            metadata={"mode": "new_primary"},
        )
        return False

    async def update_user_ticket_card(
        self,
        *,
        bot,
        ticket: Ticket,
        last_user_addition=None,
        create_if_missing: bool = False,
    ) -> bool:
        """Обновляет исходную личную карточку пользователя с последним дополнением."""

        ticket_id = ticket.ticket_id
        if last_user_addition is None and self._user_additions is not None:
            last_user_addition = self._user_additions.get_last(ticket_id)
        user_message_id = self._ticket_links.get_user_message_id(ticket_id)
        text = user_texts.render_user_ticket(
            ticket,
            room_context=self._get_room_context(ticket_id),
            last_user_addition=last_user_addition,
        )
        attachments = self._build_user_card_attachments(ticket, last_user_addition)
        if user_message_id:
            updated = await self._max_messages.edit_message(
                bot=bot,
                message_id=user_message_id,
                text=text,
                attachments=attachments,
                text_format=ParseMode.HTML,
                notify=False,
            )
            if updated:
                return True

        if not create_if_missing:
            return False

        new_mid = await self._max_messages.send_message(
            bot=bot,
            user_id=ticket.user_id,
            text=text,
            attachments=attachments,
            text_format=ParseMode.HTML,
            notify=False,
        )
        if new_mid:
            self._ticket_links.bind_user_message(ticket_id, new_mid, primary=True)
            return True
        return False

    async def update_group_ticket_card_from_callback(
        self,
        *,
        event,
        ticket: Ticket,
        notification: str,
        notify: bool = False,
    ) -> bool:
        """Обновляет нажатую карточку через callback answer."""

        ticket_id = ticket.ticket_id
        text = specialist_texts.render_group_ticket(
            ticket,
            room_context=self._get_room_context(ticket_id),
            last_clarification=self._get_last_clarification(ticket_id),
            attached_user_reply=self._get_attached_user_reply(ticket_id),
            closing_reply=self._get_closing_reply(ticket_id),
            last_internal_comment=self._get_last_internal_comment(ticket_id),
            last_user_addition=self._get_last_user_addition(ticket_id),
        )
        room_context = self._get_room_context(ticket_id)
        keyboard = build_ticket_actions_keyboard(ticket, room_context=room_context)
        attachments = self._build_card_attachments(ticket_id, keyboard)

        updated = await self._max_messages.answer_callback_with_message(
            event=event,
            text=text,
            attachments=attachments,
            notification=notification,
            text_format=ParseMode.HTML,
            notify=notify,
        )
        if updated:
            body = getattr(event.message, "body", None)
            message_id = getattr(body, "mid", None)
            if message_id:
                self._ticket_links.bind_group_message(
                    ticket_id=ticket_id,
                    group_message_id=str(message_id),
                    primary=True,
                )
            await self._sync_user_ticket_card(bot=event._ensure_bot(), ticket=ticket)
            logger.info(
                "Ticket card updated via callback answer: ticket_id=%s message_id=%s status=%s",
                ticket_id,
                message_id,
                ticket.status.value,
            )
            await self._record_card_event(
                ticket_id=ticket_id,
                event_type="ticket_card_updated",
                related_message_id=str(message_id) if message_id else None,
                metadata={"mode": "callback_answer"},
            )
            return True

        logger.warning(
            "Ticket card callback update failed, using edit fallback: ticket_id=%s",
            ticket_id,
        )
        fallback_updated = await self.update_group_ticket_card(
            bot=event._ensure_bot(),
            ticket=ticket,
            notify=notify,
        )
        if fallback_updated:
            await self._max_messages.answer_callback(
                event=event,
                notification=notification,
            )
            return True

        await self._max_messages.answer_callback(
            event=event,
            notification=f"{notification}. Карточку не удалось обновить",
        )
        await self._record_card_event(
            ticket_id=ticket_id,
            event_type="ticket_card_update_failed",
            metadata={"mode": "callback_answer"},
        )
        return False

    def _get_last_clarification(self, ticket_id: str):
        """Возвращает последнее уточнение, если сервис подключён."""

        if self._clarifications is None:
            return None
        return self._clarifications.get_last(ticket_id)

    def _get_room_context(self, ticket_id: str):
        """Возвращает hotel-specific контекст заявки."""

        if self._room_contexts is None:
            return None
        return self._room_contexts.get_context(ticket_id)

    def _get_attached_user_reply(self, ticket_id: str):
        """Возвращает прикреплённый ответ пользователя."""

        if self._clarifications is None:
            return None
        return self._clarifications.get_attached_user_reply(ticket_id)

    def _get_closing_reply(self, ticket_id: str):
        """Возвращает ответ при закрытии заявки."""

        if self._clarifications is None:
            return None
        return self._clarifications.get_closing_reply(ticket_id)

    def _get_last_internal_comment(self, ticket_id: str):
        """Возвращает последний внутренний комментарий специалиста."""

        if self._internal_comments is None:
            return None
        return self._internal_comments.get_last(ticket_id)

    def _get_last_user_addition(self, ticket_id: str):
        """Возвращает последнее прикреплённое дополнение пользователя."""

        if self._user_additions is None:
            return None
        return self._user_additions.get_last_attached(ticket_id)

    async def _sync_user_ticket_card(self, *, bot, ticket: Ticket) -> None:
        """Best-effort синхронизирует уже существующую личную карточку пользователя."""

        await self.update_user_ticket_card(bot=bot, ticket=ticket)

    def _build_card_attachments(self, ticket_id: str, keyboard) -> list[Any] | None:
        """Собирает вложения карточки: медиа ответа и кнопки."""

        attachments: list[Any] = []
        if self._clarifications is not None:
            attachments.extend(self._clarifications.get_ticket_base_attachments(ticket_id))
        clarification = self._get_last_clarification(ticket_id)
        if clarification and clarification.attachments:
            attachments.extend(clarification.attachments)
        attached_reply = self._get_attached_user_reply(ticket_id)
        if attached_reply and attached_reply.attachments:
            attachments.extend(attached_reply.attachments)
        closing_reply = self._get_closing_reply(ticket_id)
        if closing_reply and closing_reply.attachments:
            attachments.extend(closing_reply.attachments)
        addition = self._get_last_user_addition(ticket_id)
        if addition and addition.attachments:
            attachments.extend(addition.attachments)
        if keyboard:
            attachments.append(keyboard)
        return attachments or None

    def _build_user_card_attachments(self, ticket: Ticket, addition=None) -> list[Any]:
        """Сохраняет исходные медиа карточки и добавляет медиа дополнения."""

        attachments: list[Any] = []
        if self._clarifications is not None:
            attachments.extend(self._clarifications.get_ticket_base_attachments(ticket.ticket_id))
        if addition is not None and addition.attachments:
            attachments.extend(addition.attachments)
        attachments.append(build_user_ticket_keyboard(ticket))
        return attachments

    async def _record_card_event(
        self,
        *,
        ticket_id: str,
        event_type: str,
        related_message_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Пишет событие обновления карточки без влияния на UX."""

        if self._observability is None:
            return
        await self._observability.ticket_event(
            ticket_id=ticket_id,
            event_type=event_type,
            source="system",
            related_message_id=related_message_id,
            metadata=metadata or {},
        )
