"""What to say once the bot decided to speak: picks a reply mode by context and builds the reply."""

import html
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from aiogram.types import Message

from bot import taunts, voice
from bot.app import App
from bot.brain import ChatState, Context
from bot.db import Tag
from bot.markov import MarkovChain
from bot.media import MediaKind, best_photo, chat_demotivator
from bot.phrases import pick_phrase
from bot.utils import mention
from bot.wordplay import make_insult, rare_words, spice

MARKOV_LENGTHS = (3, 4, 5, 6, 8, 12)
PING_SUFFIXES = ("подтверди", "а ты что скажешь?", "скажи им", "я прав?", "ну скажи же", "ты же в теме")
ON_TOPIC_CHANCE = 0.6  # old phrase picked by a word from the message, not at random
CATCHPHRASE_CHANCE = 0.3
CHAT_SHORT_CHANCE = 0.75  # short reply from the chat's own repeats, not from the built-in set
ECHO_FRESH = 8  # how many latest messages the parrot looks at
ECHO_GLUE_CHANCE = 0.3
GIF_CHANCE = 0.25


class ReplyMode(StrEnum):
    PHRASE = "phrase"  # an old phrase from the chat, said as its own
    SHORT = "short"  # «го», «база», «ахахах»: what the chat itself says most
    MARKOV = "markov"  # nonsense generated from chat words
    ECHO = "echo"  # parrots a fresh message, sometimes glued to another phrase
    HIT = "hit"  # own lines that made people laugh before
    STICKER = "sticker"
    DEMOTIVATOR = "demotivator"
    INSULT = "insult"
    SPONGE = "sponge"  # кРиВлЯнИе
    TAG = "tag"
    NICK = "nick"
    WHO = "who"
    BURST = "burst"


# Base share of each mode, tuned on the old bot's chat history. mode_weights() shifts it by context.
BASE_WEIGHTS: dict[ReplyMode, int] = {
    ReplyMode.PHRASE: 35,
    ReplyMode.SHORT: 25,
    ReplyMode.MARKOV: 20,
    ReplyMode.DEMOTIVATOR: 10,
    ReplyMode.ECHO: 8,
    ReplyMode.HIT: 6,
    ReplyMode.STICKER: 5,
    ReplyMode.INSULT: 3,
    ReplyMode.SPONGE: 1,
}
FALLBACK = (ReplyMode.PHRASE, ReplyMode.MARKOV, ReplyMode.SHORT)


@dataclass(slots=True)
class Reply:
    """One outgoing message: HTML text, a sticker, a gif or a rendered photo."""

    mode: ReplyMode
    text: str | None = None
    plain: str | None = None  # the text as people see it; remembered so the bot doesn't repeat itself
    sticker: str | None = None
    animation: str | None = None
    photo: bytes | None = None

    @classmethod
    def say(cls, plain: str, mode: ReplyMode) -> Self:
        return cls(mode, text=html.escape(plain), plain=plain)


@dataclass(slots=True)
class Turn:
    """Everything a reply mode looks at."""

    message: Message
    text: str
    ctx: Context
    chain: MarkovChain
    state: ChatState
    app: App

    @property
    def chat_id(self) -> int:
        return self.message.chat.id

    @property
    def rng(self) -> random.Random:
        return self.app.rng

    def avoid(self) -> set[str]:
        """Lines not worth saying now: the bot's own recent ones and the message itself."""
        return {*self.state.recent_bot, self.text.strip().lower()}

    def fresh(self, plain: str) -> bool:
        lowered = plain.strip().lower()
        return bool(lowered) and lowered not in self.avoid()


async def _phrase(t: Turn) -> Reply | None:
    words = rare_words(t.text, t.chain, t.rng) if t.rng.random() < ON_TOPIC_CHANCE else []
    phrase = await pick_phrase(t.app.db, t.chat_id, words, t.avoid())
    return Reply.say(voice.casual(phrase, t.rng, verbatim=True), ReplyMode.PHRASE) if phrase else None


async def _short(t: Turn) -> Reply:
    catchphrases = t.app.settings.catchphrases
    if catchphrases and t.rng.random() < CATCHPHRASE_CHANCE:
        return Reply.say(t.rng.choice(catchphrases), ReplyMode.SHORT)
    pool = [(text, n) for text, n in await t.app.db.short_phrases(t.chat_id) if t.fresh(text)]
    if pool and t.rng.random() < CHAT_SHORT_CHANCE:
        texts, counts = zip(*pool, strict=True)
        return Reply.say(t.rng.choices(texts, weights=counts)[0], ReplyMode.SHORT)
    return Reply.say(t.rng.choice(voice.BASE_SHORT), ReplyMode.SHORT)


async def _markov(t: Turn) -> Reply | None:
    length = t.rng.choice(MARKOV_LENGTHS)
    for seed in [*rare_words(t.text, t.chain, t.rng), None]:
        out = t.chain.generate(seed, max_words=length, allow_copy=False, rng=t.rng)
        if out and t.fresh(out):
            return Reply.say(voice.casual(spice(out, t.chain, t.rng), t.rng), ReplyMode.MARKOV)
    return None


async def _echo(t: Turn) -> Reply | None:
    candidates = [x for x in list(t.state.recent)[-ECHO_FRESH:] if len(x.split()) <= 8 and t.fresh(x)]
    if not candidates:
        return None
    line = t.rng.choice(candidates)
    if t.rng.random() < ECHO_GLUE_CHANCE:
        tail = await pick_phrase(t.app.db, t.chat_id, max_words=5) or t.rng.choice(voice.BASE_SHORT)
        # the old bot glued phrases without a space: «Сгныпена ебанаДа это да»
        line = line + tail[:1].upper() + tail[1:] if t.rng.random() < 0.5 else f"{line} {tail}"
    return Reply.say(line, ReplyMode.ECHO)


async def _hit(t: Turn) -> Reply | None:
    hits = [(text, score) for text, score in await t.app.db.hits(t.chat_id) if t.fresh(text)]
    if not hits:
        return None
    texts, scores = zip(*hits, strict=True)
    return Reply.say(t.rng.choices(texts, weights=scores)[0], ReplyMode.HIT)


async def _sticker(t: Turn) -> Reply | None:
    db = t.app.db
    if t.rng.random() < GIF_CHANCE and (gif := await db.random_media(t.chat_id, MediaKind.ANIMATION)):
        return Reply(ReplyMode.STICKER, animation=gif)
    sticker = await db.random_media(t.chat_id, MediaKind.STICKER)
    return Reply(ReplyMode.STICKER, sticker=sticker) if sticker else None


async def _demotivator(t: Turn) -> Reply | None:
    photo = best_photo(t.message.photo)
    image = await chat_demotivator(
        t.app.bot,
        t.app.db,
        t.chain,
        t.chat_id,
        rng=t.rng,
        file_id=photo.file_id if photo else None,
        seed_text=t.text,
        avoid=t.avoid(),
    )
    return Reply(ReplyMode.DEMOTIVATOR, photo=image) if image else None


async def _insult(t: Turn) -> Reply | None:
    user = t.message.from_user
    if user is None:
        return None
    return Reply(ReplyMode.INSULT, text=make_insult(mention(user.id, user.full_name), t.chain, t.rng))


async def _sponge(t: Turn) -> Reply | None:
    if sum(ch.isalpha() for ch in t.text) < 4:
        return None
    return Reply.say(taunts.spongebob(t.text, t.rng), ReplyMode.SPONGE)


type ModeFn = Callable[[Turn], Awaitable[Reply | None]]
MODES: dict[ReplyMode, ModeFn] = {
    ReplyMode.PHRASE: _phrase,
    ReplyMode.SHORT: _short,
    ReplyMode.MARKOV: _markov,
    ReplyMode.ECHO: _echo,
    ReplyMode.HIT: _hit,
    ReplyMode.STICKER: _sticker,
    ReplyMode.DEMOTIVATOR: _demotivator,
    ReplyMode.INSULT: _insult,
    ReplyMode.SPONGE: _sponge,
}


def mode_weights(ctx: Context, *, photo: bool = False) -> dict[ReplyMode, int]:
    """How to answer, from what was said. Old phrases and short chat reactions dominate, like the original."""
    w = dict(BASE_WEIGHTS)
    if ctx.media:
        w[ReplyMode.MARKOV] = 5
        w[ReplyMode.ECHO] = 4
        w[ReplyMode.SPONGE] = 0
        w[ReplyMode.SHORT] += 20
        w[ReplyMode.STICKER] += 15
        if photo:
            w[ReplyMode.DEMOTIVATOR] += 60
    else:
        if ctx.question:
            w[ReplyMode.MARKOV] += 15
            w[ReplyMode.PHRASE] += 10
        if ctx.words <= 2:
            w[ReplyMode.SHORT] += 20
            w[ReplyMode.MARKOV] -= 10
        if ctx.shouting:
            w[ReplyMode.SPONGE] += 20
            w[ReplyMode.ECHO] += 10
        if ctx.reply_to_other:
            w[ReplyMode.ECHO] += 5
    if ctx.addressed:
        w[ReplyMode.PHRASE] += 10
        w[ReplyMode.MARKOV] += 10
        w[ReplyMode.SHORT] -= 10
    return {mode: max(weight, 0) for mode, weight in w.items()}


async def build_reply(
    message: Message, ctx: Context, app: App, *, state: ChatState, tag: Tag | None = None
) -> Reply | None:
    rng = app.rng
    chain = await app.chains.get(message.chat.id)
    if tag and rng.random() * 100 < app.settings.tag_chance:
        return Reply(ReplyMode.TAG, text=taunts.tagged(tag.name, tag.label, chain.random_word(rng), rng))
    turn = Turn(message, message.text or message.caption or "", ctx, chain, state, app)
    weights = {mode: w for mode, w in mode_weights(ctx, photo=bool(message.photo)).items() if w > 0}
    first = rng.choices(tuple(weights), weights=tuple(weights.values()))[0]
    for mode in dict.fromkeys((first, *FALLBACK)):
        reply = await MODES[mode](turn)
        if reply is not None:
            await _maybe_ping(reply, message, app)
            return reply
    return None


async def _maybe_ping(reply: Reply, message: Message, app: App) -> None:
    """Sometimes drags someone else into it: «..., Вася, подтверди»."""
    if reply.mode not in (ReplyMode.PHRASE, ReplyMode.MARKOV):
        return
    if app.rng.random() * 100 >= app.settings.ping_chance:
        return
    author = message.from_user.id if message.from_user else 0
    for _ in range(3):
        user = await app.db.random_user(message.chat.id)
        if user and user.user_id != author:
            ping = f"{mention(user.user_id, user.full_name)}, {app.rng.choice(PING_SUFFIXES)}"
            reply.text = f"{reply.text}\n\n{ping}"
            return
