"""Admin-only commands (ADMIN_IDS)."""

import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.app import App
from bot.handlers.filters import IN_GROUP, IsAdmin
from bot.markov import normalize
from bot.middlewares import CommandCooldownMiddleware

router = Router(name="admin")
router.message.filter(IsAdmin(), IN_GROUP)
router.message.middleware(CommandCooldownMiddleware())

MIN_NAME = 3
MAX_NAME = 30
MAX_LABEL = 60


@router.message(Command("chance"))
async def cmd_chance(message: Message, command: CommandObject, app: App) -> None:
    chat_id = message.chat.id
    if not command.args:
        current = await app.db.reply_chance(chat_id, app.settings.default_reply_chance)
        await message.reply(f"Сейчас {current}%. Поменять: /chance 0..100")
        return
    value = command.args.strip().rstrip("%")
    if not value.isdecimal() or not 0 <= int(value) <= 100:
        await message.reply("Нужно число от 0 до 100.")
        return
    await app.db.set_reply_chance(chat_id, int(value))
    await message.reply(f"Шанс влезть в разговор: {int(value)}%.")


@router.message(Command("tag"))
async def cmd_tag(message: Message, command: CommandObject, app: App) -> None:
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Формат: /tag Имя ярлык\nНапример: /tag Зигор педофайл")
        return
    name, label = parts[0], " ".join(parts[1].split())
    key = normalize(name)
    if len(key) < MIN_NAME or len(name) > MAX_NAME or len(label) > MAX_LABEL:
        await message.reply(f"Имя от {MIN_NAME} до {MAX_NAME} букв, ярлык до {MAX_LABEL} символов.")
        return
    await app.db.set_tag(message.chat.id, key, name, label)
    await message.reply(f"Запомнил: {html.escape(name)} - {html.escape(label)}.")


@router.message(Command("untag"))
async def cmd_untag(message: Message, command: CommandObject, app: App) -> None:
    key = normalize((command.args or "").strip())
    if key and await app.db.delete_tag(message.chat.id, key):
        await message.reply("Убрал.")
    else:
        await message.reply("Такого ярлыка нет. Список: /tags")


@router.message(Command("tags"))
async def cmd_tags(message: Message, app: App) -> None:
    tags = await app.db.tags(message.chat.id)
    if not tags:
        await message.reply("Ярлыков нет. Добавить: /tag Имя ярлык")
        return
    text = "\n".join(f"{html.escape(t.name)} - {html.escape(t.label)}" for t in tags)
    await message.reply(text[:4000])  # telegram cuts messages at 4096
