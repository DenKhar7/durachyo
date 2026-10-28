"""Every group message lands here: the bot learns from it, then maybe jokes, reacts or answers."""

import asyncio
import html
import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message, ReactionTypeEmoji

from bot import voice
from bot.app import App
from bot.brain import ChatState, analyze
from bot.handlers.filters import IN_GROUP
from bot.media import remember_media
from bot.nicknames import find_nick, find_tag, nick_line
from bot.responder import Reply, ReplyMode, build_reply
from bot.utils import is_addressed, mention, strip_mention, who_question

log = logging.getLogger(__name__)

router = Router(name="collect")
router.message.filter(IN_GROUP)

MEDIA_TYPES = frozenset(
    {
        ContentType.STICKER,
        ContentType.PHOTO,
        ContentType.ANIMATION,
        ContentType.VOICE,
        ContentType.VIDEO_NOTE,
        ContentType.VIDEO,
    }
)
LAUGH_WINDOW = 3  # a laugh within this many messages after the bot's line scores that line
REPLY_SHARE = 0.1  # how often an answer is a Telegram reply rather than a plain message
CALLED_REPLY_SHARE = 0.5
NICK_REACTION_SHARE = 0.5
NICK_REPLY_SHARE = 0.5
BURST_CHANCE = 0.04  # a second «ахахах» right after the answer
NO_BURST = frozenset({ReplyMode.SHORT, ReplyMode.STICKER})
TYPING_DELAY = (0.2, 1.2)
BURST_DELAY = (0.8, 2.0)
WHO_LINES = (
    "{name} {what}",
    "это {name} {what}",
    "{name} {what}, я видел",
    "очевидно же, {name} {what}",
    "{name} {what}, инфа сотка",
    "все знают, что {name} {what}",
)


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message, app: App) -> None:
    await handle(message, app, text=message.text or "", media=None)


@router.message(F.content_type.in_(MEDIA_TYPES))
async def on_media(message: Message, app: App) -> None:
    await handle(message, app, text=message.caption or "", media=message.content_type)


async def handle(message: Message, app: App, *, text: str, media: str | None) -> None:
    user = message.from_user
    if user is None or user.is_bot or message.via_bot is not None:
        return
    chat_id = message.chat.id
    called = _is_called(message, text, app)
    state = app.brain.observe(chat_id, text or None)
    laugh = voice.is_laugh(text, message.sticker.emoji if message.sticker else None)
    await _credit_laugh(app, chat_id, state, laugh=laugh)

    clean = strip_mention(text, app.me.username)
    await _learn(message, app, user.id, clean)

    if called and await _answer_who(message, app, clean):
        return
    if text and await _tease_nick(message, app, text):
        return
    await _maybe_react(message, app, laugh=laugh, media=media is not None)
    await _maybe_answer(message, app, state, text, media=media, called=called)


def _is_called(message: Message, text: str, app: App) -> bool:
    replied = message.reply_to_message.from_user if message.reply_to_message else None
    return is_addressed(
        text,
        reply_to_user_id=replied.id if replied else None,
        bot_id=app.me.id,
        bot_username=app.me.username,
        triggers=app.settings.trigger_words,
    )


def _replies_to_someone_else(message: Message) -> bool:
    author = message.from_user
    replied = message.reply_to_message.from_user if message.reply_to_message else None
    return bool(author and replied and not replied.is_bot and replied.id != author.id)


async def _credit_laugh(app: App, chat_id: int, state: ChatState, *, laugh: bool) -> None:
    """A laugh right after the bot's line scores that line, so it comes back more often."""
    if laugh and not state.scored and state.last_bot_plain and state.since_bot <= LAUGH_WINDOW:
        state.scored = True
        await app.db.add_hit(chat_id, state.last_bot_plain)


async def _learn(message: Message, app: App, user_id: int, clean: str) -> None:
    settings = app.settings
    if message.forward_origin is None and len(clean) >= settings.min_message_length:
        text = clean[: settings.max_message_length]
        await app.db.add_message(message.chat.id, user_id, text, settings.max_messages_per_chat)
        await app.chains.learn(message.chat.id, text)
    await remember_media(app.db, message)


async def _answer_who(message: Message, app: App, clean: str) -> bool:
    """«@bot кто насрал» -> pings a random person from the chat: «Вася насрал»."""
    what = who_question(clean)
    if not what or not app.cooldowns.who.ready(message.chat.id):
        return False
    user = await app.db.random_user(message.chat.id)
    author = message.from_user
    if user:
        name = mention(user.user_id, user.full_name)
    elif author:
        name = mention(author.id, author.full_name)
    else:
        return False
    line = app.rng.choice(WHO_LINES).format(name=name, what=html.escape(what))
    await _send(message, app, Reply(ReplyMode.WHO, text=line), as_reply=True)
    return True


async def _tease_nick(message: Message, app: App, text: str) -> bool:
    """Running jokes about the crew: a reaction or «Маша - свинья» when a name comes up."""
    hit = find_nick(text)
    if hit is None or app.rng.random() * 100 >= app.settings.nick_chance:
        return False
    if not app.cooldowns.nick.ready(message.chat.id):
        return False
    if hit.nick.reactions and app.rng.random() < NICK_REACTION_SHARE:
        await _react(message, app, app.rng.choice(hit.nick.reactions))
    else:
        reply = Reply.say(nick_line(hit, app.rng), ReplyMode.NICK)
        await _send(message, app, reply, as_reply=app.rng.random() < NICK_REPLY_SHARE)
    return True


async def _maybe_react(message: Message, app: App, *, laugh: bool, media: bool) -> None:
    chance = app.settings.reaction_chance * (2 if laugh or media else 1)
    if app.rng.random() * 100 < chance:
        await _react(message, app, app.rng.choice(voice.LAUGH_REACTIONS if laugh else voice.REACTIONS))


async def _maybe_answer(
    message: Message, app: App, state: ChatState, text: str, *, media: str | None, called: bool
) -> None:
    chat_id = message.chat.id
    tag = find_tag(text, await app.db.tags(chat_id)) if text else None
    ctx = analyze(
        text,
        addressed=called,
        tagged=tag is not None,
        reply_to_other=_replies_to_someone_else(message),
        media=media,
    )
    base = await app.db.reply_chance(chat_id, app.settings.default_reply_chance)
    if not app.brain.should_reply(chat_id, ctx, base, called_chance=app.settings.called_chance, rng=app.rng):
        return
    if not app.cooldowns.reply.ready(chat_id):
        return
    reply = await build_reply(message, ctx, app, state=state, tag=tag)
    if reply is None:
        return
    as_reply = app.rng.random() < (CALLED_REPLY_SHARE if called else REPLY_SHARE)
    sent = await _send(message, app, reply, as_reply=as_reply)
    if sent and reply.mode not in NO_BURST and app.rng.random() < BURST_CHANCE:
        await asyncio.sleep(app.rng.uniform(*BURST_DELAY))
        burst = Reply.say(app.rng.choice(voice.LAUGHS), ReplyMode.BURST)
        await _send(message, app, burst, as_reply=False, delay=False)


async def _react(message: Message, app: App, emoji: str) -> None:
    with suppress(TelegramAPIError):
        await app.bot.set_message_reaction(
            message.chat.id, message.message_id, [ReactionTypeEmoji(emoji=emoji)]
        )


async def _send(message: Message, app: App, reply: Reply, *, as_reply: bool, delay: bool = True) -> bool:
    """Sends like a person would (a short pause, sometimes as a Telegram reply) and remembers it."""
    if delay:
        await asyncio.sleep(app.rng.uniform(*TYPING_DELAY))
    try:
        sent = await _deliver(message, reply, as_reply=as_reply)
    except TelegramAPIError as exc:
        log.warning("send %s failed: %s", reply.mode, exc)
        return False
    if sent is None:
        return False
    app.brain.spoke(message.chat.id, reply.plain, sent.message_id)
    return True


async def _deliver(message: Message, reply: Reply, *, as_reply: bool) -> Message | None:
    if reply.photo is not None:
        photo = BufferedInputFile(reply.photo, "sglypa.jpg")
        return await (message.reply_photo(photo) if as_reply else message.answer_photo(photo))
    if reply.sticker:
        sticker = reply.sticker
        return await (message.reply_sticker(sticker) if as_reply else message.answer_sticker(sticker))
    if reply.animation:
        gif = reply.animation
        return await (message.reply_animation(gif) if as_reply else message.answer_animation(gif))
    if reply.text:
        return await (message.reply(reply.text) if as_reply else message.answer(reply.text))
    return None
