from collections.abc import Callable

from maxapi import Dispatcher

from .callbacks import register as register_callbacks
from .commands import register as register_commands
from .messages import register as register_messages
from .network_callbacks import register as register_network_callbacks
from .network_messages import register as register_network_messages

RouteRegistrar = Callable[[Dispatcher], None]


routes: list[RouteRegistrar] = [
    register_commands,
    register_callbacks,
    register_network_callbacks,
    register_network_messages,
    register_messages,
]


