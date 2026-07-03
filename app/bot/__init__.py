"""Пакет запуска MAX-бота."""

__all__ = ["main"]


def main() -> None:
    """Лениво импортирует точку запуска, чтобы сервисы не ловили import-cycle."""

    from .bot import main as run_bot

    run_bot()
