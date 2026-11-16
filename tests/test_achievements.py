from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

from aiogram.types import Message

from bot import achievements
from bot.app import App
from bot.db import Duelist
from bot.handlers import collect, games
from bot.middlewares import TrackUsersMiddleware
from tests.helpers import CHAT, make_message
from tests.test_commands import fake_message, said


def announced(bot: AsyncMock) -> list[str]:
    return [str(call.args[1]) for call in bot.send_message.await_args_list]


async def feed(app: App, text: str, user_id: int = 10, **extra: object) -> None:
    message = make_message(text, user_id=user_id, **extra)  # type: ignore[arg-type]
    await collect.handle(message, app, text=text, media=None)


async def test_unlock_announces_once(app: App, bot: AsyncMock) -> None:
    assert await achievements.unlock(app, CHAT, 10, "Вася", "crit")
    assert not await achievements.unlock(app, CHAT, 10, "Вася", "crit")
    (text,) = announced(bot)
    assert "Вася" in text and achievements.BY_CODE["crit"].title in text


async def test_night_owl_uses_chat_timezone(app: App, bot: AsyncMock) -> None:
    await app.db.set_reply_chance(CHAT, 0)
    await feed(app, "не спится", date=datetime(2026, 1, 1, 0, 30, tzinfo=UTC))  # 3:30 in Moscow
    assert await app.db.achievements(CHAT, 10) == ["night_owl"]


async def test_spammer_and_caps_counters(app: App) -> None:
    await app.db.set_reply_chance(CHAT, 0)
    for _ in range(20):
        await feed(app, "ВЫ ЧТО ТУТ ТВОРИТЕ", date=datetime(2026, 1, 1, 12, tzinfo=UTC))
    assert set(await app.db.achievements(CHAT, 10)) == {"spammer", "shouter"}


async def test_clown_counts_laughs_from_others_only(app: App) -> None:
    await app.db.set_reply_chance(CHAT, 0)
    await app.db.upsert_user(CHAT, 10, "Вася", None)
    noon = datetime(2026, 1, 1, 12, tzinfo=UTC)
    for i in range(10):
        await feed(app, f"шутка {i}", user_id=10, date=noon)
        await feed(app, "АХАХАХАХ", user_id=11, date=noon)
        await feed(app, "ахахах", user_id=12, date=noon)  # laughing at a laugh: nothing
    assert "clown" in await app.db.achievements(CHAT, 10)
    assert await app.db.bump_counter(CHAT, 10, "laughs", 0) == 10


async def test_ghost_after_a_month(app: App) -> None:
    await app.db.upsert_user(CHAT, 10, "Вася", None)
    await app.db._conn.execute("UPDATE users SET last_seen = last_seen - 40 * 86400")
    await TrackUsersMiddleware()(AsyncMock(), make_message("я вернулся"), {"app": app})
    assert await app.db.achievements(CHAT, 10) == ["ghost"]


async def test_after_duel(app: App) -> None:
    stats = Duelist(10, "Вася", wins=10, losses=0, streak=5)
    await achievements.after_duel(app, CHAT, stats, name="Вася", roll=20)
    assert set(await app.db.achievements(CHAT, 10)) == {"first_blood", "duelist", "immortal", "crit"}


async def test_achievements_command(app: App) -> None:
    message = fake_message()
    await games.cmd_achievements(cast(Message, message), app)
    assert "позорище" in said(message)
    await app.db.unlock_achievement(CHAT, 10, "fumble")
    message = fake_message()
    await games.cmd_achievements(cast(Message, message), app)
    text = said(message)
    assert achievements.BY_CODE["fumble"].title in text and f"(1/{len(achievements.ALL)})" in text


def test_every_counter_achievement_has_a_goal() -> None:
    assert all(a.goal > 0 for a in achievements.ALL if a.counter)
    assert len(achievements.BY_CODE) == len(achievements.ALL)
