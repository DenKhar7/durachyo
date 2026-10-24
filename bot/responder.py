import html
import random
from collections.abc import Awaitable, Callable

from aiogram.types import Message

from bot import mock
from bot.chains import ChainStore
from bot.db import Database
from bot.markov import MarkovChain, normalize
from bot.utils import mention

Mode = Callable[[Message, MarkovChain, Database, random.Random], Awaitable[str | None]]


async def _seeded(message: Message, chain: MarkovChain, db: Database, rng: random.Random) -> str | None:
    text = message.text or ""
    words = [w for w in text.split() if len(normalize(w)) >= 3 and chain.known(w)]
    rng.shuffle(words)
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
    "seeded": (_seeded, 45),
    "free": (_free, 15),
    "quote": (_quote, 15),
    "sponge": (_sponge, 10),
    "insult": (_insult, 15),
}


async def build_reply(
    message: Message, db: Database, chains: ChainStore, rng: random.Random | None = None
) -> str | None:
    """Returns ready-to-send HTML or None."""
    rng = rng or random.Random()
    chain = await chains.get(message.chat.id)
    names = tuple(MODES)
    first = rng.choices(names, weights=[MODES[n][1] for n in names])[0]
    for name in dict.fromkeys((first, "seeded", "free")):
        reply = await MODES[name][0](message, chain, db, rng)
        if reply:
            return reply
    return None
