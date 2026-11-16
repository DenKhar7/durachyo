import asyncio
import logging
import random
from collections.abc import Collection
from enum import StrEnum

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, PhotoSize

from bot.db import Database
from bot.demotivator import make_demotivator
from bot.markov import MarkovChain
from bot.phrases import pick_phrase
from bot.wordplay import rare_words

log = logging.getLogger(__name__)

MAX_PHOTO_SIDE = 1280
SUBTITLE_CHANCE = 0.5


class MediaKind(StrEnum):
    STICKER = "sticker"
    ANIMATION = "animation"
    PHOTO = "photo"


def best_photo(sizes: list[PhotoSize] | None, max_side: int = MAX_PHOTO_SIDE) -> PhotoSize | None:
    # telegram sends every photo in several sizes, smallest first
    if not sizes:
        return None
    fitting = [p for p in sizes if max(p.width, p.height) <= max_side]
    return (fitting or sizes)[-1]


async def remember_media(db: Database, message: Message) -> None:
    chat_id = message.chat.id
    if message.sticker:
        s = message.sticker
        await db.add_media(chat_id, MediaKind.STICKER, s.file_unique_id, s.file_id, emoji=s.emoji)
    elif message.animation:
        a = message.animation
        await db.add_media(chat_id, MediaKind.ANIMATION, a.file_unique_id, a.file_id)
    elif photo := best_photo(message.photo):
        await db.add_media(chat_id, MediaKind.PHOTO, photo.file_unique_id, photo.file_id)


async def download(bot: Bot, file_id: str) -> bytes | None:
    try:
        stream = await bot.download(file_id)
    except (TelegramAPIError, aiohttp.ClientError, TimeoutError) as exc:
        log.warning("download %s failed: %s", file_id, exc)
        return None
    return stream.read() if stream else None


async def chat_demotivator(
    bot: Bot,
    db: Database,
    chain: MarkovChain,
    chat_id: int,
    *,
    rng: random.Random,
    file_id: str | None = None,
    seed_text: str = "",
    title: str | None = None,
    avoid: Collection[str] = frozenset(),
) -> bytes | None:
    """Demotivator out of a chat photo with a caption in the chat's own words.

    Without file_id takes a random photo the chat has posted before.
    """
    file_id = file_id or await db.random_media(chat_id, MediaKind.PHOTO)
    if not file_id:
        return None
    if not title:
        words = rare_words(seed_text, chain, rng)
        title = await pick_phrase(db, chat_id, words, avoid, max_words=8)
        title = title or chain.generate(max_words=6, rng=rng)
    if not title:
        return None
    subtitle = chain.generate(max_words=6, rng=rng) if rng.random() < SUBTITLE_CHANCE else None
    image = await download(bot, file_id)
    if image is None:
        return None
    try:
        # pillow is blocking, keep it off the event loop
        return await asyncio.to_thread(make_demotivator, image, title, subtitle)
    except OSError as exc:
        log.warning("can't draw a demotivator, broken image? %s", exc)
        return None
