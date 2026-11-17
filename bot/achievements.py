"""Ачивки. Most of them are counters that tick on every message, the rest come from duels."""

import html
import logging
from contextlib import suppress
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from bot.app import App
from bot.brain import analyze
from bot.db import Duelist
from bot.duel import SIDES
from bot.utils import mention

log = logging.getLogger(__name__)

NIGHT = range(3, 5)  # 3:00-4:59 in the chat's timezone
GHOST_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True, slots=True)
class Achievement:
    code: str
    emoji: str
    title: str
    description: str
    counter: str | None = None  # unlocked when this counter reaches goal
    goal: int = 0


ALL = (
    Achievement("night_owl", "🌙", "Ночной Сторож", "писал в чат ночью"),
    Achievement("spammer", "🗣", "Спаммер", "15 сообщений за 2 минуты"),
    Achievement("chatterbox", "💬", "Болтун", "1000 сообщений", "messages", 1000),
    Achievement("veteran", "📜", "Старожила", "5000 сообщений", "messages", 5000),
    Achievement("shouter", "📢", "Орун", "20 сообщений капсом", "caps", 20),
    Achievement("stickerman", "🃏", "Стикерщик", "100 стикеров", "stickers", 100),
    Achievement("summoner", "🔔", "Призыватель", "звал сглыпу 50 раз", "calls", 50),
    Achievement("clown", "🤡", "Клоун", "10 раз рассмешил чат", "laughs", 10),
    Achievement("ghost", "👻", "Призрак", "вернулся после месяца молчания"),
    Achievement("first_blood", "🩸", "First Blood", "первая победа в дуэли"),
    Achievement("duelist", "⚔️", "Дуэлянт", "10 побед в дуэлях"),
    Achievement("immortal", "🍀", "Лакер", "5 побед подряд"),
    Achievement("punching_bag", "🥊", "Груша для битья", "10 поражений в дуэлях"),
    Achievement("crit", "🎯", "Лакер", "выбросил 20 в дуэли"),
    Achievement("detective", "🕵", "Детектив", "угадал автора 10 раз", "quiz_points", 10),
    Achievement("sherlock", "🔎", "Шерлок", "угадал автора 50 раз", "quiz_points", 50),
    Achievement("loser", "🤡", "Крещение", "впервые стал лохом дня", "loser_days", 1),
    Achievement("born_loser", "🪦", "Прирождённый лох", "был лохом дня 5 раз", "loser_days", 5),
    Achievement("astrologer", "🔮", "Астролог", "смотрел гороскоп 10 дней,красава", "horoscopes", 10),
    Achievement("fumble", "🤦", "Анлакер", "выбросил 1 в дуэли"),
)
BY_CODE = {a.code: a for a in ALL}


async def unlock(app: App, chat_id: int, user_id: int, name: str | None, code: str) -> bool:
    if not await app.db.unlock_achievement(chat_id, user_id, code):
        return False
    a = BY_CODE[code]
    text = (
        f"🏆 {mention(user_id, name)} получает новую ачивку {a.emoji} <b>{html.escape(a.title)}</b>\n"
        f"<i>{html.escape(a.description)}</i>"
    )
    with suppress(TelegramAPIError):
        await app.bot.send_message(chat_id, text)
    return True


async def progress(app: App, chat_id: int, user_id: int, name: str | None, counter: str) -> int:
    value = await app.db.bump_counter(chat_id, user_id, counter)
    for a in ALL:
        if a.counter == counter and value >= a.goal:
            await unlock(app, chat_id, user_id, name, a.code)
    return value


async def on_message(app: App, message: Message, *, text: str, called: bool, laughed_at: int | None) -> None:
    """laughed_at: whose message this one laughs at, if it is a laugh."""
    user = message.from_user
    if user is None:
        return
    chat_id, name = message.chat.id, user.full_name
    if message.date.astimezone(ZoneInfo(app.settings.timezone)).hour in NIGHT:
        await unlock(app, chat_id, user.id, name, "night_owl")
    if not app.cooldowns.spam.ready((chat_id, user.id)):
        await unlock(app, chat_id, user.id, name, "spammer")
    await progress(app, chat_id, user.id, name, "messages")
    if text and analyze(text).shouting:
        await progress(app, chat_id, user.id, name, "caps")
    if message.sticker:
        await progress(app, chat_id, user.id, name, "stickers")
    if called:
        await progress(app, chat_id, user.id, name, "calls")
    if laughed_at is not None and laughed_at != user.id:
        funny = await app.db.get_user(chat_id, laughed_at)
        await progress(app, chat_id, laughed_at, funny.full_name if funny else None, "laughs")


async def on_return(app: App, chat_id: int, user_id: int, name: str, away_seconds: float) -> None:
    if away_seconds >= GHOST_SECONDS:
        await unlock(app, chat_id, user_id, name, "ghost")


async def after_duel(app: App, chat_id: int, stats: Duelist, *, name: str, roll: int) -> None:
    user_id = stats.user_id
    earned = {
        "first_blood": stats.wins >= 1,
        "duelist": stats.wins >= 10,
        "immortal": stats.streak >= 5,
        "punching_bag": stats.losses >= 10,
        "crit": roll == SIDES,
        "fumble": roll == 1,
    }
    for code, ok in earned.items():
        if ok:
            await unlock(app, chat_id, user_id, name, code)


def card(name: str, codes: list[str]) -> str:
    got = [BY_CODE[c] for c in codes if c in BY_CODE]
    lines = [f"🏆 <b>Ачивки {html.escape(name)}</b> ({len(got)}/{len(ALL)})"]
    lines += [f"{a.emoji} {html.escape(a.title)} - {html.escape(a.description)}" for a in got]
    if not got:
        lines.append("пока ничего, позорище")
    elif len(got) < len(ALL):
        lines.append(f"\nещё {len(ALL) - len(got)} закрыто")
    return "\n".join(lines)
