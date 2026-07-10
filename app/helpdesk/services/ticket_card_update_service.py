"""Обновление групповой карточки заявки в MAX."""

import logging
from typing import Any

from maxapi.enums.parse_mode import ParseMode

from app.bot.services.max_message_service import MaxMessageService
from app.helpdesk.keyboards.helpdesk_keyboards import build_ticket_actions_keyboard
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.services.knowledge_base_service import KnowledgeBaseService
from app.helpdesk.services.postgres_ticket_link_service import PostgresTicketLinkService
from app.helpdesk.services.ticket_clarification_service import TicketClarificationService
from app.helpdesk.services.ticket_link_service import TicketLinkService
from app.helpdesk.texts import specialist_texts
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
        knowledge_base: KnowledgeBaseService | None = None,
        room_contexts=None,
        observability: ObservabilityService | None = None,
    ) -> None:
        self._ticket_links = ticket_links
        self._group_chat_id = group_chat_id
        self._max_messages = max_messages or MaxMessageService()
        self._clarifications = clarifications
        self._knowledge_base = knowledge_base
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
            last_specialist_comment=self._get_last_specialist_comment(ticket_id),
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
            last_specialist_comment=self._get_last_specialist_comment(ticket_id),
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

    def _get_last_specialist_comment(self, ticket_id: str):
        """Возвращает последний внутренний комментарий специалиста."""

        if self._knowledge_base is None:
            return None
        return self._knowledge_base.get_last_ticket_comment(ticket_id)

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
        if keyboard:
            attachments.append(keyboard)
        return attachments or None

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
