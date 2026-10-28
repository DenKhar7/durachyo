from datetime import UTC, datetime
from unittest.mock import AsyncMock

from bot.app import App
from bot.brain import Brain
from bot.revive import in_quiet_hours, revive_once
from tests.helpers import CHAT, FakeClock

NOON = datetime(2026, 1, 1, 12, tzinfo=UTC)
NIGHT = datetime(2026, 1, 1, 3, tzinfo=UTC)


def test_quiet_hours_plain_range() -> None:
    assert in_quiet_hours(3, "1-10")
    assert not in_quiet_hours(10, "1-10")
    assert not in_quiet_hours(0, "1-10")


def test_quiet_hours_over_midnight() -> None:
    assert in_quiet_hours(23, "22-8")
    assert in_quiet_hours(2, "22-8")
    assert not in_quiet_hours(12, "22-8")


def test_quiet_hours_disabled() -> None:
    assert not in_quiet_hours(5, "0-0")


async def test_revive_once_writes_into_every_quiet_chat_once(app: App, bot: AsyncMock) -> None:
    chats = (CHAT, CHAT - 1)
    app.settings = app.settings.model_copy(update={"allowed_chat_ids": frozenset(chats)})
    clock = FakeClock()
    app.brain = Brain(clock)
    for chat in chats:
        await app.db.add_message(chat, 10, "привет как дела у вас", keep=100)
        app.brain.observe(chat)
    clock.t += 5 * 3600

    assert await revive_once(app, now=NOON) == 2
    assert bot.send_message.await_count == 2
    assert await revive_once(app, now=NOON) == 0


async def test_revive_once_keeps_quiet_at_night(app: App, bot: AsyncMock) -> None:
    clock = FakeClock()
    app.brain = Brain(clock)
    app.brain.observe(CHAT)
    clock.t += 5 * 3600
    assert await revive_once(app, now=NIGHT) == 0
    bot.send_message.assert_not_awaited()
