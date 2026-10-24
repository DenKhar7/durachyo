from aiogram import F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message

from bot.config import Settings
from bot.db import Database
from bot.middlewares import CommandCooldownMiddleware
from bot.utils import GROUP_TYPES


class IsAdmin(Filter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return message.from_user is not None and message.from_user.id in settings.admin_ids


router = Router(name="admin")
router.message.filter(IsAdmin())
router.message.middleware(CommandCooldownMiddleware())


@router.message(Command("chance"), F.chat.type.in_(GROUP_TYPES))
async def cmd_chance(message: Message, command: CommandObject, db: Database, settings: Settings) -> None:
    if not command.args:
        current = await db.reply_chance(message.chat.id, settings.default_reply_chance)
        await message.reply(f"Сейчас {current}%. Поменять: /chance 0..100")
        return
    try:
        value = int(command.args.strip().rstrip("%"))
    except ValueError:
        value = -1
    if not 0 <= value <= 100:
        await message.reply("Нужно число от 0 до 100.")
        return
    await db.set_reply_chance(message.chat.id, value)
    await message.reply(f"Шанс влезть в разговор: {value}%.")
