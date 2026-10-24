import html
import random
from collections.abc import Awaitable, Callable

from aiogram.types import Message

from bot import mock
from bot.brain import Context
from bot.chains import ChainStore
from bot.db import Database, Tag
from bot.markov import MarkovChain, normalize
from bot.utils import mention

Mode = Callable[[Message, MarkovChain, Database, random.Random], Awaitable[str | None]]


async def _seeded(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    """Continues the chat's chain from a word of the message. Rare words first: they make the reply on-topic."""
    text = message.text or ""
    unique = {normalize(w): w for w in text.split() if len(normalize(w)) >= 3 and chain.known(w)}
    words = sorted(unique.values(), key=lambda w: (chain.frequency(w), rng.random()))
    for word in words[:5]:
        out = chain.generate(word, max_words=20, rng=rng)
        if out and out.lower() != text.lower():
            return html.escape(out)
    return None


async def _free(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    out = chain.generate(rng=rng)
    return html.escape(out) if out else None


async def _quote(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    user = message.from_user
    row = await db.random_message(message.chat.id, user.id)
    if row is None or row[1] == message.text:
        return None
    return mock.quote_back(mention(user.id, user.full_name), row[1], rng)


async def _sponge(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    text = message.text or ""
    if sum(ch.isalpha() for ch in text) < 4:
        return None
    return html.escape(mock.spongebob(text, rng))


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


async def _insult(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    user = message.from_user
    return make_insult(mention(user.id, user.full_name), chain, rng)


MODES: dict[str, Mode] = {
    "seeded": _seeded,
    "quote": _quote,
    "free": _free,
    "insult": _insult,
    "sponge": _sponge,
}
PING_SUFFIXES = ("подтверди", "а ты что скажешь?", "скажи им", "я прав?", "ну скажи же", "ты же в теме")


def mode_weights(ctx: Context) -> dict[str, int]:
    """Picks how to answer from what was said: questions get answers, shouting gets mocked, one-worders get nonsense."""
    w = {"seeded": 60, "quote": 15, "free": 10, "insult": 10, "sponge": 5}
    if ctx.question:
        w["seeded"] += 30
        w["insult"] += 5
    if ctx.words <= 2:
        w["seeded"] -= 40
        w["free"] += 25
        w["sponge"] += 10
    if ctx.shouting:
        w["sponge"] += 40
    if ctx.addressed:
        w["insult"] += 10
    if ctx.reply_to_other:
        w["quote"] += 10
    return {k: max(v, 1) for k, v in w.items()}


def find_tag(text: str, tags: list[Tag]) -> Tag | None:
    """A tag whose word appears in the text, allowing short Russian endings (Егор -> Егора, Егору)."""
    words = [normalize(w) for w in text.split()]
    for tag in tags:
        for w in words:
            if w.startswith(tag.key) and len(w) - len(tag.key) <= 3:
                return tag
    return None


async def _ping(message: Message, db: Database, rng: random.Random) -> str | None:
    author = message.from_user.id if message.from_user else 0
    for _ in range(3):
        user = await db.random_user(message.chat.id)
        if user and user.user_id != author:
            return f"{mention(user.user_id, user.full_name)}, {rng.choice(PING_SUFFIXES)}"
    return None


async def build_reply(
    message: Message,
    db: Database,
    chains: ChainStore,
    ctx: Context,
    *,
    tag: Tag | None = None,
    tag_chance: int = 0,
    ping_chance: int = 0,
    rng: random.Random | None = None,
) -> str | None:
    """Returns ready-to-send HTML or None."""
    rng = rng or random.Random()
    chain = await chains.get(message.chat.id)
    if tag and rng.random() * 100 < tag_chance:
        return mock.tagged(tag.name, tag.label, chain.random_word(rng), rng)
    weights = mode_weights(ctx)
    first = rng.choices(tuple(weights), weights=tuple(weights.values()))[0]
    for name in dict.fromkeys((first, "seeded", "free")):
        reply = await MODES[name](message, chain, db, rng)
        if not reply:
            continue
        if name in ("seeded", "free") and rng.random() * 100 < ping_chance:
            ping = await _ping(message, db, rng)
            if ping:
                reply = f"{reply}\n\n{ping}"
        return reply
    return None
