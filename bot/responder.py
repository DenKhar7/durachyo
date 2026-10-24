import html
import random
from collections.abc import Awaitable, Callable

from aiogram.types import Message

from bot import mock
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
        out = chain.generate(word, rng=rng)
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


async def _insult(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    user = message.from_user
    return mock.insult(mention(user.id, user.full_name), chain.random_word(rng), rng)


MODES: dict[str, tuple[Mode, int]] = {
    "insult": (_insult, 40),
    "quote": (_quote, 30),
    "seeded": (_seeded, 22),
    "sponge": (_sponge, 5),
    "free": (_free, 3),
}


def find_tag(text: str, tags: list[Tag]) -> Tag | None:
    """A tag whose word appears in the text, allowing short Russian endings (Егор -> Егора, Егору)."""
    words = [normalize(w) for w in text.split()]
    for tag in tags:
        for w in words:
            if w.startswith(tag.key) and len(w) - len(tag.key) <= 3:
                return tag
    return None


async def build_reply(
    message: Message,
    db: Database,
    chains: ChainStore,
    tag_chance: int = 0,
    rng: random.Random | None = None,
) -> str | None:
    """Returns ready-to-send HTML or None."""
    rng = rng or random.Random()
    chain = await chains.get(message.chat.id)
    if tag_chance and rng.random() * 100 < tag_chance:
        tag = find_tag(message.text or "", await db.tags(message.chat.id))
        if tag:
            return mock.tagged(tag.name, tag.label, chain.random_word(rng), rng)
    names = tuple(MODES)
    first = rng.choices(names, weights=[MODES[n][1] for n in names])[0]
    for name in dict.fromkeys((first, "seeded", "free")):
        reply = await MODES[name][0](message, chain, db, rng)
        if reply:
            return reply
    return None
