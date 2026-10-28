from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.app import App
from bot.handlers import collect
from bot.responder import ReplyMode
from tests.helpers import CHAT, make_message


@pytest.fixture
def deliver(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    fake = AsyncMock(return_value=SimpleNamespace(message_id=7))
    monkeypatch.setattr(collect, "_deliver", fake)
    monkeypatch.setattr(collect, "TYPING_DELAY", (0, 0))
    return fake


async def handle(app: App, text: str) -> None:
    await collect.handle(make_message(text), app, text=text, media=None)


async def test_learns_every_message_and_stays_quiet_at_zero_chance(app: App, deliver: AsyncMock) -> None:
    await app.db.set_reply_chance(CHAT, 0)
    await handle(app, "пиво холодное есть")
    assert await app.db.texts(CHAT) == ["пиво холодное есть"]
    deliver.assert_not_awaited()


async def test_who_question_pings_someone_from_the_chat(app: App, deliver: AsyncMock) -> None:
    await app.db.upsert_user(CHAT, 11, "Петя", None)
    await handle(app, "@sglyper_bot кто насрал")
    assert deliver.await_args is not None
    reply = deliver.await_args.args[1]
    assert reply.mode is ReplyMode.WHO
    assert "tg://user?id=11" in reply.text and "насрал" in reply.text
    assert app.brain.state(CHAT).last_bot_id == 7


async def test_laugh_after_bot_line_scores_it(app: App, deliver: AsyncMock) -> None:
    await app.db.set_reply_chance(CHAT, 0)
    app.brain.spoke(CHAT, "normalno", 5)
    await handle(app, "АХАХАХАХ")
    assert await app.db.hits(CHAT) == [("normalno", 1)]


async def test_ignores_other_bots(app: App, deliver: AsyncMock) -> None:
    message = make_message("сглыпа ответь")
    assert message.from_user is not None
    author = message.from_user.model_copy(update={"is_bot": True})
    await collect.handle(
        message.model_copy(update={"from_user": author}), app, text="сглыпа ответь", media=None
    )
    assert await app.db.texts(CHAT) == []
    deliver.assert_not_awaited()
