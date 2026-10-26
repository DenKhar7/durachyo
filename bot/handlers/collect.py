import asyncio
import html
import logging
import random
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message, ReactionTypeEmoji, User

from bot import voice
from bot.brain import Brain, analyze
from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database
from bot.nicknames import find_nick, nick_line
from bot.responder import Reply, best_photo, build_reply, find_tag
from bot.utils import GROUP_TYPES, Cooldown, is_addressed, mention, strip_mention, who_question

log = logging.getLogger(__name__)

router = Router(name="collect")
in_group = F.chat.type.in_(GROUP_TYPES)
MEDIA = frozenset({"sticker", "photo", "animation", "voice", "video_note", "video"})
BURST_CHANCE = 0.04
NICK_COOLDOWN = 30.0
_reply_cooldown = Cooldown()
WHO_COOLDOWN = 3.0
WHO_LINES = (
    "{name} {what}",
    "это {name} {what}",
    "{name} {what}, я видел",
    "очевидно же, {name} {what}",
    "{name} {what}, инфа сотка",
    "все знают, что {name} {what}",
)
_rng = random.Random()


@router.message(in_group, F.text, ~F.text.startswith("/"))
async def on_text(
    message: Message, bot: Bot, bot_me: User, settings: Settings, db: Database, chains: ChainStore, brain: Brain
) -> None:
    await handle(message, message.text, None, bot, bot_me, settings, db, chains, brain)


@router.message(in_group, F.content_type.in_(MEDIA))
async def on_media(
    message: Message, bot: Bot, bot_me: User, settings: Settings, db: Database, chains: ChainStore, brain: Brain
) -> None:
    await handle(message, message.caption or "", message.content_type, bot, bot_me, settings, db, chains, brain)


async def handle(
    message: Message,
    text: str,
    media: str | None,
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
    reply_user = message.reply_to_message.from_user if message.reply_to_message else None
    called = is_addressed(
        text,
        reply_to_user_id=reply_user.id if reply_user else None,
        bot_id=bot_me.id,
        bot_username=bot_me.username,
        triggers=settings.trigger_words,
    )
    state = brain.observe(chat_id, text or None)

    laugh = voice.is_laugh(text, message.sticker.emoji if message.sticker else None)
    if laugh and not state.scored and state.last_bot_plain and state.since_bot <= 3:
        state.scored = True
        await db.add_hit(chat_id, state.last_bot_plain)

    clean = strip_mention(text, bot_me.username)
    if message.forward_origin is None and len(clean) >= settings.min_message_length:
        clean = clean[: settings.max_message_length]
        await db.add_message(chat_id, user.id, clean, settings.max_messages_per_chat)
        await chains.learn(chat_id, clean)
    await remember_media(db, message)

    if called and text:
        what = who_question(clean)
        if what and _reply_cooldown.ready(("who", chat_id), WHO_COOLDOWN):
            await answer_who(message, what, db, brain)
            return

    if text and await tease_nick(message, text, bot, settings, brain):
        return
    await maybe_react(bot, message, laugh=laugh, media=media is not None, chance=settings.reaction_chance)

    tag = find_tag(text, await db.tags(chat_id)) if text else None
    ctx = analyze(
        text,
        addressed=called,
        tagged=tag is not None,
        reply_to_other=bool(reply_user and not reply_user.is_bot and reply_user.id != user.id),
        media=media,
    )
    base = await db.reply_chance(chat_id, settings.default_reply_chance)
    if not brain.should_reply(chat_id, ctx, base, settings.called_chance):
        return
    if not _reply_cooldown.ready(chat_id, settings.reply_cooldown):
        return
    reply = await build_reply(
        message, ctx, db=db, chains=chains, state=state, settings=settings, bot=bot, tag=tag, rng=_rng
    )
    if reply is None:
        return
    as_reply = _rng.random() < (0.5 if called else 0.1)
    sent = await send(message, reply, as_reply)
    if sent is None:
        return
    brain.spoke(chat_id, reply.plain, sent.message_id)
    if reply.mode not in ("short", "sticker") and _rng.random() < BURST_CHANCE:
        await asyncio.sleep(_rng.uniform(0.8, 2.0))
        extra = _rng.choice(voice.LAUGHS)
        follow = await send(message, Reply(text=extra, plain=extra, mode="burst"), False, delay=False)
        if follow:
            brain.spoke(chat_id, extra, follow.message_id)


async def answer_who(message: Message, what: str, db: Database, brain: Brain) -> None:
    """'@bot кто насрал' -> pings a random person from the chat: 'Вася насрал'."""
    user = await db.random_user(message.chat.id)
    author = message.from_user
    name = mention(user.user_id, user.full_name) if user else mention(author.id, author.full_name)
    line = _rng.choice(WHO_LINES).format(name=name, what=html.escape(what))
    sent = await send(message, Reply(text=line, mode="who"), True)
    if sent:
        brain.spoke(message.chat.id, None, sent.message_id)


async def tease_nick(message: Message, text: str, bot: Bot, settings: Settings, brain: Brain) -> bool:
    """Built-in running jokes about the crew: a reaction or a one-liner when someone's name comes up."""
    hit = find_nick(text)
    if hit is None or _rng.random() * 100 >= settings.nick_chance:
        return False
    if not _reply_cooldown.ready(("nick", message.chat.id), NICK_COOLDOWN):
        return False
    if hit.nick.reactions and _rng.random() < 0.5:
        with suppress(TelegramAPIError):
            await bot.set_message_reaction(
                message.chat.id, message.message_id, [ReactionTypeEmoji(emoji=_rng.choice(hit.nick.reactions))]
            )
        return True
    line = nick_line(hit, _rng)
    sent = await send(message, Reply(text=line, plain=line, mode="nick"), _rng.random() < 0.5)
    if sent:
        brain.spoke(message.chat.id, line, sent.message_id)
    return True


async def remember_media(db: Database, message: Message) -> None:
    chat_id = message.chat.id
    if message.sticker:
        s = message.sticker
        await db.add_media(chat_id, "sticker", s.file_unique_id, s.file_id, s.emoji)
    elif message.animation:
        a = message.animation
        await db.add_media(chat_id, "animation", a.file_unique_id, a.file_id)
    elif message.photo:
        p = best_photo(message.photo)
        await db.add_media(chat_id, "photo", p.file_unique_id, p.file_id)


async def maybe_react(bot: Bot, message: Message, *, laugh: bool, media: bool, chance: int) -> None:
    if _rng.random() * 100 >= chance * (2 if laugh or media else 1):
        return
    emoji = _rng.choice(voice.LAUGH_REACTIONS if laugh else voice.REACTIONS)
    with suppress(TelegramAPIError):
        await bot.set_message_reaction(message.chat.id, message.message_id, [ReactionTypeEmoji(emoji=emoji)])


async def send(message: Message, reply: Reply, as_reply: bool, delay: bool = True) -> Message | None:
    if delay:
        await asyncio.sleep(_rng.uniform(0.2, 1.2))
    try:
        if reply.photo is not None:
            photo = BufferedInputFile(reply.photo, "sglypa.jpg")
            return await (message.reply_photo(photo) if as_reply else message.answer_photo(photo))
        if reply.sticker:
            return await (message.reply_sticker(reply.sticker) if as_reply else message.answer_sticker(reply.sticker))
        if reply.animation:
            anim = reply.animation
            return await (message.reply_animation(anim) if as_reply else message.answer_animation(anim))
        if reply.text:
            return await (message.reply(reply.text) if as_reply else message.answer(reply.text))
    except TelegramAPIError as exc:
        log.warning("send %s failed: %s", reply.mode, exc)
    return None
