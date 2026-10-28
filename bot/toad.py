"""Жаба дня: a toad meme for each person in a chat, the same one all day.

Memes come from two pools:
- the internet: frog/toad meme subreddits through meme-api.com (free, no key; Reddit itself blocks servers);
- the chat itself: reply to any picture, gif or sticker with "/жаба добавь".
Wednesday gets «it is wednesday my dudes» toads, other days don't.
"""

import asyncio
import hashlib
import logging
import random
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp

from bot.db import Database, ToadMeme

log = logging.getLogger(__name__)

API_URL = "https://meme-api.com/gimme/{subreddit}/50"
SUBREDDITS = ("frogmemes", "frog_irl", "frogsinhats", "itswednesdaymydudes")
WEDNESDAY_SOURCE = "itswednesdaymydudes"
WEDNESDAY = 2
POOL_TARGET = 300  # refill while the shared pool is smaller
POOL_MAX = 1000  # only links are stored (~200 bytes each); the oldest go beyond this
REFILL_EVERY = 12 * 3600  # new memes appear on Reddit; look for them twice a day
OWN_SHARE = 0.5  # how often the chat's own collection wins over the internet one
TIMEOUT = aiohttp.ClientTimeout(total=20)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

ADJECTIVES = (
    "Болотная", "Бархатная", "Токсичная", "Королевская", "Сонная", "Пупырчатая", "Космическая",
    "Депрессивная", "Гигачадовая", "Квантовая", "Анимешная", "Пьяная", "Бородавчатая", "Душная",
    "Элитная", "Подвальная", "Контуженная", "Олимпийская", "Шизанутая", "Ламповая",
)  # fmt: skip
NOUNS = (
    "пельмень", "философ", "бомж", "император", "гопник", "сигма", "скуф", "альтушка",
    "программист", "дед инсайд", "барон", "шаурма", "ниндзя", "абобус", "тиктокер", "сантехник",
    "депутат", "киберкотлета", "бабка у подъезда", "стример",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Rarity:
    name: str
    weight: int


RARITIES = (
    Rarity("обычная", 60),
    Rarity("редкая", 25),
    Rarity("эпическая", 12),
    Rarity("легендарная 👑", 3),
)
LEGENDARY = RARITIES[-1]


@dataclass(frozen=True, slots=True)
class Toad:
    name: str
    rarity: Rarity
    power: int


@dataclass(frozen=True, slots=True)
class MemeLink:
    kind: str  # "photo" or "animation"
    url: str
    source: str


def toad_seed(chat_id: int, user_id: int, day: date) -> int:
    """Stable across restarts, unlike hash(): Python randomizes str hashes per process."""
    digest = hashlib.sha256(f"{chat_id}:{user_id}:{day.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def toad_of_the_day(chat_id: int, user_id: int, day: date) -> Toad:
    rng = random.Random(toad_seed(chat_id, user_id, day))
    rarity = rng.choices(RARITIES, weights=[r.weight for r in RARITIES])[0]
    power = rng.randint(90, 100) if rarity is LEGENDARY else rng.randint(1, 89)
    return Toad(f"{rng.choice(ADJECTIVES)} жаба-{rng.choice(NOUNS)}", rarity, power)


def parse_memes(payload: dict[str, Any], source: str) -> list[MemeLink]:
    """Safe-for-work pictures and gifs from a meme-api.com answer."""
    links = []
    for meme in payload.get("memes") or ():
        url = str(meme.get("url") or "")
        if meme.get("nsfw") or meme.get("spoiler") or not url.startswith("https://"):
            continue
        path = url.lower().split("?")[0]
        if path.endswith(".gif"):
            links.append(MemeLink("animation", url, source))
        elif path.endswith(IMAGE_EXTENSIONS):
            links.append(MemeLink("photo", url, source))
    return links


async def fetch_memes(session: aiohttp.ClientSession, subreddit: str) -> list[MemeLink]:
    try:
        async with session.get(API_URL.format(subreddit=subreddit)) as response:
            response.raise_for_status()
            return parse_memes(await response.json(), subreddit)
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        log.warning("toad memes from r/%s failed: %s", subreddit, exc)
        return []


class ToadPool:
    """Keeps the shared meme pool in the DB stocked; one refill at a time."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_refill = float("-inf")

    async def refill(self, db: Database, *, force: bool = False) -> int:
        async with self._lock:
            stale = time.monotonic() - self._last_refill > REFILL_EVERY
            if not force and not stale and await db.toad_meme_count() >= POOL_TARGET:
                return 0
            self._last_refill = time.monotonic()
            async with aiohttp.ClientSession(
                timeout=TIMEOUT, headers={"User-Agent": "sglypa-bot"}
            ) as session:
                batches = await asyncio.gather(*(fetch_memes(session, s) for s in SUBREDDITS))
            links = [link for batch in batches for link in batch]
            added = await db.add_toad_memes([(link.kind, link.source, link.url) for link in links])
            await db.prune_toads(date.today(), keep_shared=POOL_MAX)
            log.info("toad pool: +%s memes", added)
            return added

    async def pick(
        self, db: Database, chat_id: int, user_id: int, day: date, rng: random.Random
    ) -> ToadMeme | None:
        """Today's meme of this person: the one already given, or a fresh one nobody here got today."""
        given = await db.toad_of_day(chat_id, user_id, day)
        if given:
            return given
        if await db.toad_meme_count() < POOL_TARGET:
            await self.refill(db)
        elif time.monotonic() - self._last_refill > REFILL_EVERY:
            asyncio.get_running_loop().create_task(self._refill_quietly(db))
        wednesday = day.weekday() == WEDNESDAY
        order = (True, False) if rng.random() < OWN_SHARE else (False, True)
        for own in order:
            meme = await db.pick_toad_meme(chat_id, day, own=own, wednesday=wednesday)
            if meme:
                await db.give_toad(chat_id, user_id, day, meme.id)
                return meme
        return None

    async def _refill_quietly(self, db: Database) -> None:
        try:
            await self.refill(db)
        except Exception:  # background refill must never kill the bot; it is retried later
            log.exception("toad refill failed")
