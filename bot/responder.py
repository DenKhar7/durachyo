import asyncio
import html
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, PhotoSize

from bot import mock, voice
from bot.brain import ChatState, Context
from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database, Tag
from bot.demotivator import make_demotivator
from bot.markov import MarkovChain, normalize
from bot.utils import mention

log = logging.getLogger(__name__)

SPICE_CHANCE = 0.2
MARKOV_LENGTHS = (3, 4, 5, 6, 8, 12)
PING_SUFFIXES = ("подтверди", "а ты что скажешь?", "скажи им", "я прав?", "ну скажи же", "ты же в теме")
FALLBACK = ("phrase", "markov", "short")
_VOWELS = set("аеёиоуыэюяaeiouy")


def blend(a: str, b: str) -> str:
    """Glues the head of one word to the tail of another at a vowel: пидорства + база -> пидаза."""
    cut_a = next((i + 1 for i in range(len(a) // 2, len(a)) if a[i] in _VOWELS), len(a) // 2 + 1)
    cut_b = next((i for i in range(len(b) // 2, 0, -1) if b[i] in _VOWELS), len(b) // 2)
    return a[:cut_a] + b[cut_b:]


def spice(text: str, chain: MarkovChain, rng: random.Random) -> str:
    """Sometimes swaps one word for a mash-up of two chat words."""
    words = text.split()
    slots = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha()]
    vocab = [w for w in chain.vocabulary() if len(w) >= 4 and w.isalpha()]
    if not slots or len(vocab) < 2 or rng.random() >= SPICE_CHANCE:
        return text
    i = rng.choice(slots)
    other = rng.choice([w for w in vocab if w != words[i].lower()] or vocab)
    words[i] = blend(words[i], other) if rng.random() < 0.5 else blend(other, words[i])
    return " ".join(words)


ADJ_ENDINGS = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие")


def make_insult(name_html: str, chain: MarkovChain, rng: random.Random, chat_share: float = 0.8) -> str:
    """Mostly built from chat words; sometimes falls back to the stock insults."""
    vocab = [w for w in chain.vocabulary() if 3 <= len(w) <= 16 and not w.isdigit()]
    phrase = chain.generate(rng.choice(vocab), max_words=6, rng=rng) if vocab else None
    if not vocab or not phrase or rng.random() >= chat_share:
        return mock.insult(name_html, rng.choice(vocab) if vocab else None, rng)
    adjectives = [w for w in vocab if len(w) >= 5 and w.endswith(ADJ_ENDINGS)]
    adj = rng.choice(adjectives) if adjectives else rng.choice(mock.ADJECTIVES)
    nouns = [w for w in vocab if len(w) >= 4 and w not in adjectives]
    word = rng.choice(nouns or vocab)
    return mock.chat_insult(name_html, phrase, word, adj, rng)


def find_tag(text: str, tags: list[Tag]) -> Tag | None:
    """A tag whose word appears in the text, allowing short Russian endings (Егор -> Егора, Егору)."""
    words = [normalize(w) for w in text.split()]
    for tag in tags:
        for w in words:
            if w.startswith(tag.key) and len(w) - len(tag.key) <= 3:
                return tag
    return None


@dataclass(slots=True)
class Reply:
    text: str | None = None
    sticker: str | None = None
    animation: str | None = None
    photo: bytes | None = None
    plain: str | None = None
    mode: str = ""


@dataclass(slots=True)
class Turn:
    message: Message
    text: str
    ctx: Context
    chain: MarkovChain
    db: Database
    state: ChatState
    settings: Settings
    bot: Bot
    rng: random.Random

    @property
    def chat_id(self) -> int:
        return self.message.chat.id

    def fresh(self, plain: str) -> bool:
        lo = plain.strip().lower()
        return bool(lo) and lo != self.text.strip().lower() and lo not in self.state.recent_bot


def _say(plain: str, mode: str) -> Reply:
    return Reply(text=html.escape(plain), plain=plain, mode=mode)


def best_photo(sizes: list[PhotoSize] | None, max_side: int = 1280) -> PhotoSize | None:
    if not sizes:
        return None
    fitting = [p for p in sizes if max(p.width, p.height) <= max_side]
    return (fitting or sizes)[-1]


def rare_words(text: str, chain: MarkovChain, rng: random.Random, n: int = 3) -> list[str]:
    unique = {normalize(w) for w in text.split() if len(normalize(w)) >= 4 and chain.known(w)}
    return sorted(unique, key=lambda k: (chain.frequency(k), rng.random()))[:n]


async def phrase_skip(db: Database, chat_id: int) -> int:
    """How many newest messages are too fresh to be repeated: a phrase only lands once people forgot it."""
    total, _ = await db.stats(chat_id)
    return min(300, max(20, total // 4))


async def pick_phrase(
    db: Database,
    chat_id: int,
    words: list[str] | tuple[str, ...] = (),
    avoid: set[str] | frozenset[str] = frozenset(),
    max_words: int = 12,
) -> str | None:
    skip = await phrase_skip(db, chat_id)
    for word in words:
        p = await db.old_phrase(chat_id, skip, word=word, max_words=max_words)
        if p and p.strip().lower() not in avoid:
            return p
    for _ in range(3):
        p = await db.old_phrase(chat_id, skip, max_words=max_words)
        if p and p.strip().lower() not in avoid:
            return p
    return None


def _avoid(t: Turn) -> set[str]:
    return set(t.state.recent_bot) | {t.text.strip().lower()}


async def _phrase(t: Turn) -> Reply | None:
    """An old phrase of anyone in the chat, said as its own. Related to the message when possible."""
    words = rare_words(t.text, t.chain, t.rng) if t.rng.random() < 0.6 else []
    p = await pick_phrase(t.db, t.chat_id, words, _avoid(t))
    return _say(voice.casual(p, t.rng, verbatim=True), "phrase") if p else None


async def _short(t: Turn) -> Reply | None:
    if t.settings.catchphrases and t.rng.random() < 0.3:
        return _say(t.rng.choice(t.settings.catchphrases), "short")
    pool = [(p, n) for p, n in await t.db.short_phrases(t.chat_id) if t.fresh(p)]
    if pool and t.rng.random() < 0.75:
        texts, counts = zip(*pool)
        return _say(t.rng.choices(texts, weights=counts)[0], "short")
    return _say(t.rng.choice(voice.BASE_SHORT), "short")


async def _markov(t: Turn) -> Reply | None:
    n = t.rng.choice(MARKOV_LENGTHS)
    seeds = [*rare_words(t.text, t.chain, t.rng), None]
    for seed in seeds:
        out = t.chain.generate(seed, max_words=n, allow_copy=False, rng=t.rng)
        if out and t.fresh(out):
            return _say(voice.casual(spice(out, t.chain, t.rng), t.rng), "markov")
    return None


async def _echo(t: Turn) -> Reply | None:
    """Parrots something said a moment ago, sometimes glued to another phrase like the old bot did."""
    candidates = [x for x in list(t.state.recent)[-8:] if len(x.split()) <= 8 and t.fresh(x)]
    if not candidates:
        return None
    p = t.rng.choice(candidates)
    if t.rng.random() < 0.3:
        tail = await pick_phrase(t.db, t.chat_id, max_words=5) or t.rng.choice(voice.BASE_SHORT)
        p = p + tail[:1].upper() + tail[1:] if t.rng.random() < 0.5 else f"{p} {tail}"
    return _say(p, "echo")


async def _hit(t: Turn) -> Reply | None:
    """Its own lines that made people laugh before: catchphrases grow out of these."""
    hits = [(x, s) for x, s in await t.db.hits(t.chat_id) if t.fresh(x)]
    if not hits:
        return None
    texts, scores = zip(*hits)
    return _say(t.rng.choices(texts, weights=scores)[0], "hit")


async def _sticker(t: Turn) -> Reply | None:
    if t.rng.random() < 0.25:
        gif = await t.db.random_media(t.chat_id, "animation")
        if gif:
            return Reply(animation=gif, mode="sticker")
    sticker = await t.db.random_media(t.chat_id, "sticker")
    return Reply(sticker=sticker, mode="sticker") if sticker else None


async def chat_demotivator(
    bot: Bot,
    db: Database,
    chain: MarkovChain,
    chat_id: int,
    file_id: str | None = None,
    *,
    seed_text: str = "",
    title: str | None = None,
    avoid: set[str] | frozenset[str] = frozenset(),
    rng: random.Random | None = None,
) -> bytes | None:
    """Demotivator from a chat photo (given or random remembered one) captioned with the chat's own words."""
    rng = rng or random.Random()
    file_id = file_id or await db.random_media(chat_id, "photo")
    if not file_id:
        return None
    if not title:
        title = await pick_phrase(db, chat_id, rare_words(seed_text, chain, rng), avoid, max_words=8)
        title = title or chain.generate(max_words=6, rng=rng)
    if not title:
        return None
    subtitle = chain.generate(max_words=6, rng=rng) if rng.random() < 0.5 else None
    try:
        data = (await bot.download(file_id)).read()
        return await asyncio.to_thread(make_demotivator, data, title, subtitle)
    except (TelegramAPIError, AttributeError, OSError) as exc:
        log.warning("demotivator failed: %s", exc)
        return None


async def _demotivator(t: Turn) -> Reply | None:
    photo = best_photo(t.message.photo)
    data = await chat_demotivator(
        t.bot, t.db, t.chain, t.chat_id, photo.file_id if photo else None,
        seed_text=t.text, avoid=_avoid(t), rng=t.rng,
    )
    return Reply(photo=data, mode="demotivator") if data else None


async def _insult(t: Turn) -> Reply | None:
    user = t.message.from_user
    if user is None:
        return None
    return Reply(text=make_insult(mention(user.id, user.full_name), t.chain, t.rng), mode="insult")


async def _sponge(t: Turn) -> Reply | None:
    if sum(ch.isalpha() for ch in t.text) < 4:
        return None
    return _say(mock.spongebob(t.text, t.rng), "sponge")


Mode = Callable[[Turn], Awaitable[Reply | None]]
MODES: dict[str, Mode] = {
    "phrase": _phrase,
    "short": _short,
    "markov": _markov,
    "echo": _echo,
    "hit": _hit,
    "sticker": _sticker,
    "demotivator": _demotivator,
    "insult": _insult,
    "sponge": _sponge,
}


def mode_weights(ctx: Context, *, photo: bool = False) -> dict[str, int]:
    """How to answer, from what was said. Old phrases and short chat reactions dominate, like the original."""
    w = {
        "phrase": 35, "short": 25, "markov": 20, "echo": 8, "hit": 6,
        "sticker": 5, "demotivator": 10, "insult": 3, "sponge": 1,
    }
    if ctx.media:
        w.update(markov=5, echo=4, sponge=0)
        w["short"] += 20
        w["sticker"] += 15
        if photo:
            w["demotivator"] += 60
    else:
        if ctx.question:
            w["markov"] += 15
            w["phrase"] += 10
        if ctx.words <= 2:
            w["short"] += 20
            w["markov"] -= 10
        if ctx.shouting:
            w["sponge"] += 20
            w["echo"] += 10
        if ctx.reply_to_other:
            w["echo"] += 5
    if ctx.addressed:
        w["phrase"] += 10
        w["markov"] += 10
        w["short"] -= 10
    return {k: max(v, 0) for k, v in w.items()}


async def _ping(message: Message, db: Database, rng: random.Random) -> str | None:
    author = message.from_user.id if message.from_user else 0
    for _ in range(3):
        user = await db.random_user(message.chat.id)
        if user and user.user_id != author:
            return f"{mention(user.user_id, user.full_name)}, {rng.choice(PING_SUFFIXES)}"
    return None


async def build_reply(
    message: Message,
    ctx: Context,
    *,
    db: Database,
    chains: ChainStore,
    state: ChatState,
    settings: Settings,
    bot: Bot,
    tag: Tag | None = None,
    rng: random.Random | None = None,
) -> Reply | None:
    rng = rng or random.Random()
    chain = await chains.get(message.chat.id)
    if tag and rng.random() * 100 < settings.tag_chance:
        return Reply(text=mock.tagged(tag.name, tag.label, chain.random_word(rng), rng), mode="tag")
    turn = Turn(message, message.text or message.caption or "", ctx, chain, db, state, settings, bot, rng)
    weights = {k: v for k, v in mode_weights(ctx, photo=bool(message.photo)).items() if v > 0}
    first = rng.choices(tuple(weights), weights=tuple(weights.values()))[0]
    for name in dict.fromkeys((first, *FALLBACK)):
        reply = await MODES[name](turn)
        if reply is None:
            continue
        if reply.mode in ("phrase", "markov") and rng.random() * 100 < settings.ping_chance:
            ping = await _ping(message, db, rng)
            if ping:
                reply.text = f"{reply.text}\n\n{ping}"
        return reply
    return None
