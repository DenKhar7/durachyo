import asyncio
import random

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message, User

from bot.brain import Brain, analyze
from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database
from bot.responder import build_reply, find_tag
from bot.utils import GROUP_TYPES, Cooldown, is_addressed, strip_mention

router = Router(name="collect")
_reply_cooldown = Cooldown()


@router.message(F.chat.type.in_(GROUP_TYPES), F.text, ~F.text.startswith("/"))
async def on_text(
    message: Message,
    bot: Bot,
    bot_me: User,
    settings: Settings,
    db: Database,
    chains: ChainStore,
    brain: Brain,
) -> None:
    user = message.from_user
    if user is None or user.is_bot or message.via_bot is not None:
        return
    chat_id = message.chat.id
    text = message.text
    reply_user = message.reply_to_message.from_user if message.reply_to_message else None
    addressed = is_addressed(
        text,
        reply_to_user_id=reply_user.id if reply_user else None,
        bot_id=bot_me.id,
        bot_username=bot_me.username,
        triggers=settings.trigger_words,
    )
    brain.observe(chat_id)

    clean = strip_mention(text, bot_me.username)
    if message.forward_origin is None and len(clean) >= settings.min_message_length:
        clean = clean[: settings.max_message_length]
        await db.add_message(chat_id, user.id, clean, settings.max_messages_per_chat)
        await chains.learn(chat_id, clean)

    tag = find_tag(text, await db.tags(chat_id))
    ctx = analyze(
        text,
        addressed=addressed,
        tagged=tag is not None,
        reply_to_other=bool(reply_user and not reply_user.is_bot and reply_user.id != user.id),
    )
    base = await db.reply_chance(chat_id, settings.default_reply_chance)
    if not brain.should_reply(chat_id, ctx, base):
        return
    if not _reply_cooldown.ready(chat_id, settings.reply_cooldown):
        return
    reply = await build_reply(
        message, db, chains, ctx, tag=tag, tag_chance=settings.tag_chance, ping_chance=settings.ping_chance
    )
    if not reply:
        return
    await bot.send_chat_action(chat_id, ChatAction.TYPING, message_thread_id=message.message_thread_id)
    await asyncio.sleep(min(0.6 + len(reply) / 60, 3.0))
    if addressed or random.random() < 0.6:
        await message.reply(reply)
    else:
        await message.answer(reply)
    brain.spoke(chat_id)
