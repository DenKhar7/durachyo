import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.brain import Brain
from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, collect, commands
from bot.middlewares import TrackUsersMiddleware, WhitelistMiddleware
from bot.revive import revive_loop

log = logging.getLogger("sglypa")

COMMANDS = [
    BotCommand(command="sglyp", description="Бред по мотивам чата"),
    BotCommand(command="all", description="Пингануть всех"),
    BotCommand(command="forgetme", description="Забыть мои сообщения"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not settings.allowed_chat_ids:
        log.warning("ALLOWED_CHAT_IDS is empty: bot will leave every group. Chat ids are logged on leave.")

    db = await Database.open(settings.db_path)
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    try:
        me = await bot.get_me()
        chains = ChainStore(db, settings.markov_order)
        brain = Brain()
        dp = Dispatcher(settings=settings, db=db, chains=chains, brain=brain, bot_me=me)
        dp.update.outer_middleware(WhitelistMiddleware())
        dp.message.outer_middleware(TrackUsersMiddleware())
        dp.include_routers(admin.router, commands.router, collect.router)

        await bot.set_my_commands(COMMANDS)
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Started as @%s (id=%s)", me.username, me.id)
        revive = asyncio.create_task(revive_loop(bot, db, chains, brain, settings))
        try:
            await dp.start_polling(bot, allowed_updates=["message", "my_chat_member"])
        finally:
            revive.cancel()
    finally:
        await bot.session.close()
        await db.close()


def run() -> None:
    asyncio.run(main())
