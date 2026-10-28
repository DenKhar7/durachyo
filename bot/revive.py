"""Breaks the silence: writes into a chat that has been quiet for a few hours."""

import asyncio
import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramAPIError

from bot import voice
from bot.app import App
from bot.phrases import pick_phrase
from bot.utils import mention

log = logging.getLogger(__name__)

CHECK_EVERY = 600
PING_CHANCE = 0.4


def in_quiet_hours(hour: int, spec: str) -> bool:
    """spec like "1-10" or "22-8" (over midnight); equal ends switch quiet hours off."""
    start, end = (int(x) for x in spec.split("-"))
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


async def revive_once(app: App, now: datetime | None = None) -> int:
    """Writes into every allowed chat that went quiet. Once per silence, never at night."""
    settings = app.settings
    now = now or datetime.now(ZoneInfo(settings.timezone))
    if in_quiet_hours(now.hour, settings.quiet_hours):
        return 0
    idle = settings.revive_after_hours * 3600
    revived = 0
    for chat_id in settings.allowed_chat_ids:
        if app.brain.needs_revive(chat_id, idle) and await _revive_chat(app, chat_id):
            revived += 1
    return revived


async def _revive_chat(app: App, chat_id: int) -> bool:
    rng = app.rng
    text = await pick_phrase(app.db, chat_id)
    text = text or (await app.chains.get(chat_id)).generate(max_words=8, rng=rng)
    if not text:
        return False
    body = html.escape(voice.casual(text, rng, verbatim=True))
    user = await app.db.random_user(chat_id)
    if user and rng.random() < PING_CHANCE:
        body = f"{mention(user.user_id, user.full_name)}, {body}"
    try:
        sent = await app.bot.send_message(chat_id, body)
    except TelegramAPIError as exc:
        log.warning("revive in %s failed: %s", chat_id, exc)
        return False
    app.brain.spoke(chat_id, text, sent.message_id)
    return True


async def revive_loop(app: App) -> None:
    while True:
        await asyncio.sleep(CHECK_EVERY)
        try:
            await revive_once(app)
        except Exception:  # the loop has to outlive any single failure; the traceback is logged
            log.exception("revive failed")
