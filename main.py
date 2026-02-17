import asyncio

from config.config import get_config, setup_logging


async def amain() -> None:
    from app.bot.bot import main as bot_main
    await bot_main()


def main() -> None:
    cfg = get_config()
    setup_logging(cfg.logs)
    asyncio.run(amain())


if __name__ == "__main__":
    main()