import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.app import App
from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, collect, commands, fun, games
from bot.middlewares import TrackUsersMiddleware, WhitelistMiddleware
from bot.revive import revive_loop

log = logging.getLogger("sglypa")

COMMANDS = [
    BotCommand(command="sglyp", description="Бред по мотивам чата"),
    BotCommand(command="demotiv", description="Демотиватор"),
    BotCommand(command="duel", description="Дуэль на d20"),
    BotCommand(command="top", description="Топ дуэлянтов"),
    BotCommand(command="stats", description="Моя статистика дуэлей"),
    BotCommand(command="ach", description="Мои ачивки"),
    BotCommand(command="quiz", description="Кто это сказал?"),
    BotCommand(command="loser", description="Лох дня"),
    BotCommand(command="horoscope", description="Гороскоп на сегодня"),
    BotCommand(command="all", description="Пингануть всех"),
    BotCommand(command="forgetme", description="Забыть мои сообщения"),
    BotCommand(command="help", description="Помощь"),
]
ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]


def build_dispatcher(app: App) -> Dispatcher:
    dp = Dispatcher(app=app)
    dp.update.outer_middleware(WhitelistMiddleware())
    dp.message.outer_middleware(TrackUsersMiddleware())
    dp.include_routers(admin.router, commands.router, games.router, fun.router, collect.router)
    return dp


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
        app = App.create(settings, bot, db, await bot.get_me())
        dp = build_dispatcher(app)
        await bot.set_my_commands(COMMANDS)
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Started as @%s (id=%s)", app.me.username, app.me.id)
        revive = asyncio.create_task(revive_loop(app))
        try:
            await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
        finally:
            revive.cancel()
            with suppress(asyncio.CancelledError):
                await revive
    finally:
        await bot.session.close()
        await db.close()


def run() -> None:
    asyncio.run(main())
