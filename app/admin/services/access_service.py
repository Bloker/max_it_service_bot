"""Правила доступа пользователей, IT-специалистов и администраторов."""

from collections.abc import Iterable

from app.helpdesk.models.ticket import Ticket


def is_admin(user_id: int, admin_ids: Iterable[int]) -> bool:
    """Проверяет, входит ли пользователь в список администраторов."""

    return user_id in set(admin_ids)


def is_it_specialist(user_id: int, specialist_ids: Iterable[int]) -> bool:
    """Проверяет, входит ли пользователь в список IT-специалистов."""

    return user_id in set(specialist_ids)


def is_user(user_id: int) -> bool:
    """Проверяет базовую валидность пользовательского ID."""

    return user_id > 0


def can_view_user_menu(
    user_id: int,
    admin_ids: Iterable[int],
    specialist_ids: Iterable[int],
    user_ids: Iterable[int] = (),
    approved_user_ids: Iterable[int] = (),
) -> bool:
    """Определяет, доступно ли пользователю основное меню."""

    if not is_user(user_id):
        return False

    allowed_users = (
        set(admin_ids)
        | set(specialist_ids)
        | set(user_ids)
        | set(approved_user_ids)
    )
    if not allowed_users:
        # Режим совместимости: если allow-list не задан, пускаем всех
        # пользователей с положительным ID.
        return True
    return user_id in allowed_users


def can_view_service_functions(
    user_id: int,
    admin_ids: Iterable[int],
    specialist_ids: Iterable[int],
) -> bool:
    """Проверяет доступ к сервисным функциям HelpDesk."""

    return is_admin(user_id, admin_ids) or is_it_specialist(user_id, specialist_ids)


def can_use_network_tools(
    user_id: int,
    admin_ids: Iterable[int],
    specialist_ids: Iterable[int],
) -> bool:
    """Проверяет доступ к сетевым инструментам."""

    return can_view_service_functions(user_id, admin_ids, specialist_ids)


def can_take_ticket(
    user_id: int,
    admin_ids: Iterable[int],
    specialist_ids: Iterable[int],
) -> bool:
    """Проверяет право взять заявку в работу."""

    return can_view_service_functions(user_id, admin_ids, specialist_ids)


def can_change_ticket_status(
    actor_user_id: int,
    ticket: Ticket,
    admin_ids: Iterable[int],
    specialist_ids: Iterable[int],
) -> bool:
    """Проверяет право менять статус конкретной заявки."""

    if is_admin(actor_user_id, admin_ids):
        return True
    if not is_it_specialist(actor_user_id, specialist_ids):
        return False
    if ticket.assigned_to is None:
        return True
    return ticket.assigned_to == actor_user_id


def can_do_admin_actions(user_id: int, admin_ids: Iterable[int]) -> bool:
    """Проверяет доступ к административным действиям."""

    return is_admin(user_id, admin_ids)


def can_manage_settings(user_id: int, admin_ids: Iterable[int]) -> bool:
    """Проверяет доступ к настройкам бота."""

    return can_do_admin_actions(user_id, admin_ids)
