import asyncio
import html
import logging
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot import voice
from bot.brain import Brain
from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database
from bot.responder import pick_phrase
from bot.utils import mention

log = logging.getLogger(__name__)

CHECK_EVERY = 600


def in_quiet_hours(hour: int, spec: str) -> bool:
    start, end = (int(x) for x in spec.split("-"))
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


async def revive_once(
    bot: Bot,
    db: Database,
    chains: ChainStore,
    brain: Brain,
    settings: Settings,
    rng: random.Random,
    now: datetime | None = None,
) -> int:
    """Breaks the silence in chats that went quiet. Once per silence, never at night."""
    now = now or datetime.now(ZoneInfo(settings.timezone))
    if in_quiet_hours(now.hour, settings.quiet_hours):
        return 0
    sent = 0
    for chat_id in settings.allowed_chat_ids:
        if not brain.needs_revive(chat_id, settings.revive_after_hours * 3600):
            continue
        text = await pick_phrase(db, chat_id) or (await chains.get(chat_id)).generate(max_words=8, rng=rng)
        if not text:
            continue
        body = html.escape(voice.casual(text, rng, verbatim=True))
        user = await db.random_user(chat_id)
        if user and rng.random() < 0.4:
            body = f"{mention(user.user_id, user.full_name)}, {body}"
        try:
            sent = await bot.send_message(chat_id, body)
        except TelegramAPIError as exc:
            log.warning("revive in %s failed: %s", chat_id, exc)
            continue
        brain.spoke(chat_id, text, sent.message_id)
        sent += 1
    return sent


async def revive_loop(bot: Bot, db: Database, chains: ChainStore, brain: Brain, settings: Settings) -> None:
    rng = random.Random()
    while True:
        await asyncio.sleep(CHECK_EVERY)
        try:
            await revive_once(bot, db, chains, brain, settings, rng)
        except Exception:
            log.exception("revive failed")
