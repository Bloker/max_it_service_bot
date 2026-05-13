"""Список регистраторов обработчиков MAX dispatcher."""

from collections.abc import Callable

from maxapi import Dispatcher

from .callbacks import register as register_callbacks
from .commands import register as register_commands
from .messages import register as register_messages
from .network_callbacks import register as register_network_callbacks

RouteRegistrar = Callable[[Dispatcher], None]


# Порядок важен: команды и callback-обработчики должны сработать раньше
# общего обработчика сообщений.
routes: list[RouteRegistrar] = [
    register_commands,
    register_callbacks,
    register_network_callbacks,
    register_messages,
]
