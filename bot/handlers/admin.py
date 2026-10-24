import html

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message

from bot.config import Settings
from bot.db import Database
from bot.markov import normalize
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


MAX_NAME = 30
MAX_LABEL = 60


@router.message(Command("tag"), F.chat.type.in_(GROUP_TYPES))
async def cmd_tag(message: Message, command: CommandObject, db: Database) -> None:
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Формат: /tag Имя ярлык\nНапример: /tag Зигор педофайл")
        return
    name, label = parts[0], " ".join(parts[1].split())
    key = normalize(name)
    if len(key) < 3 or len(name) > MAX_NAME or len(label) > MAX_LABEL:
        await message.reply(f"Имя от 3 до {MAX_NAME} букв, ярлык до {MAX_LABEL} символов.")
        return
    await db.set_tag(message.chat.id, key, name, label)
    await message.reply(f"Запомнил: {html.escape(name)} - {html.escape(label)}.")


@router.message(Command("untag"), F.chat.type.in_(GROUP_TYPES))
async def cmd_untag(message: Message, command: CommandObject, db: Database) -> None:
    key = normalize((command.args or "").strip())
    if key and await db.delete_tag(message.chat.id, key):
        await message.reply("Убрал.")
    else:
        await message.reply("Такого ярлыка нет. Список: /tags")


@router.message(Command("tags"), F.chat.type.in_(GROUP_TYPES))
async def cmd_tags(message: Message, db: Database) -> None:
    tags = await db.tags(message.chat.id)
    if not tags:
        await message.reply("Ярлыков нет. Добавить: /tag Имя ярлык")
        return
    lines = (f"{html.escape(t.name)} - {html.escape(t.label)}" for t in tags)
    await message.reply("\n".join(lines))
