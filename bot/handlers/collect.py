import random

from aiogram import F, Router
from aiogram.types import Message, User

from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database
from bot.responder import build_reply
from bot.utils import GROUP_TYPES, Cooldown, is_addressed, strip_mention

router = Router(name="collect")
_reply_cooldown = Cooldown()


@router.message(F.chat.type.in_(GROUP_TYPES), F.text, ~F.text.startswith("/"))
async def on_text(message: Message, bot_me: User, settings: Settings, db: Database, chains: ChainStore) -> None:
    user = message.from_user
    if user is None or user.is_bot or message.via_bot is not None:
        return
    chat_id = message.chat.id
    reply_to = message.reply_to_message
    addressed = is_addressed(
        message.text,
        reply_to_user_id=reply_to.from_user.id if reply_to and reply_to.from_user else None,
        bot_id=bot_me.id,
        bot_username=bot_me.username,
        triggers=settings.trigger_words,
    )

    clean = strip_mention(message.text, bot_me.username)
    if message.forward_origin is None and len(clean) >= settings.min_message_length:
        clean = clean[: settings.max_message_length]
        await db.add_message(chat_id, user.id, clean, settings.max_messages_per_chat)
        await chains.learn(chat_id, clean)

    if not addressed:
        chance = await db.reply_chance(chat_id, settings.default_reply_chance)
        if random.random() * 100 >= chance:
            return
    if not _reply_cooldown.ready(chat_id, settings.reply_cooldown):
        return
    reply = await build_reply(message, db, chains)
    if reply:
        await message.reply(reply)
