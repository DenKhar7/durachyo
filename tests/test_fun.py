from datetime import date
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message

from bot import daily
from bot.app import App
from bot.db import Database
from bot.handlers import fun
from tests.helpers import CHAT
from tests.test_commands import fake_message, said

DAY = date(2026, 11, 20)


def command(name: str, args: str | None = None) -> CommandObject:
    return CommandObject(prefix="/", command=name, args=args)


async def crowd(app: App, n: int = 3) -> None:
    for i, name in enumerate(["Вася", "Петя", "Маша", "Егор"][:n]):
        await app.db.upsert_user(CHAT, 10 + i, name, None)


@pytest.fixture(autouse=True)
def no_drama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fun, "DRAMA_PAUSE", 0)


def test_daily_helpers() -> None:
    assert daily.day_seed("x", 1, DAY) == daily.day_seed("x", 1, DAY)
    assert daily.sign_of(10) == daily.sign_of(10) in daily.SIGNS


async def test_daily_pick_keeps_the_first_one(db: Database) -> None:
    assert await db.set_daily_pick(-1, DAY, "loser", "10") == "10"
    assert await db.set_daily_pick(-1, DAY, "loser", "11") == "10"
    assert await db.daily_pick(-1, date(2026, 11, 21), "loser") is None


async def test_loser_once_a_day_with_top(app: App) -> None:
    await crowd(app)
    message = fake_message()
    await fun.cmd_loser(cast(Message, message), command("лох"), app)
    calls = [str(c.args[0]) for c in message.answer.await_args_list]
    assert (len(calls) == len(daily.LOSER_DRAMA) + 1 and "Лох дня" in calls[-1]) or "лох" in calls[-1]
    again = fake_message()
    await fun.cmd_loser(cast(Message, again), command("лох"), app)
    assert "уже выбран" in said(again)
    top = fake_message()
    await fun.cmd_loser(cast(Message, top), command("лох", "топ"), app)
    assert "- 1" in said(top)


async def test_horoscope_is_stable(app: App) -> None:
    await crowd(app)
    for text in ["пиво холодное есть", "го в доту сегодня вечером"] * 15:
        await app.db.add_message(CHAT, 11, text, keep=100)
    first, second = fake_message(), fake_message()
    await fun.cmd_horoscope(cast(Message, first), app)
    await fun.cmd_horoscope(cast(Message, second), app)
    assert "Знак:" in said(first) and said(first) == said(second)


def answer_query(app: App, user_id: int, picked: int) -> AsyncMock:
    query = AsyncMock()
    query.data = f"quiz:{picked}"
    query.from_user = SimpleNamespace(id=user_id, full_name=f"user{user_id}")
    query.message = AsyncMock(spec=Message)
    query.message.chat = SimpleNamespace(id=CHAT)
    query.message.message_id = 77
    query.message.edit_text = AsyncMock()
    return query


async def test_quiz_round(app: App) -> None:
    message = fake_message()
    await fun.cmd_quiz(cast(Message, message), command("ктосказал"), app)
    assert "Мало данных" in said(message)
    await crowd(app)
    await app.db.add_message(CHAT, 11, "я пью пиво дома", keep=100)
    message = fake_message()
    message.answer.return_value = SimpleNamespace(message_id=77)
    await fun.cmd_quiz(cast(Message, message), command("ктосказал"), app)
    call = message.answer.await_args
    assert call is not None and "я пью пиво дома" in call.args[0]
    buttons = [b[0].callback_data for b in call.kwargs["reply_markup"].inline_keyboard]
    assert sorted(buttons) == ["quiz:10", "quiz:11", "quiz:12"]

    author = answer_query(app, 11, 11)
    await fun.on_quiz_answer(cast(CallbackQuery, author), app)
    assert "ты сказал" in author.answer.await_args.args[0]
    wrong = answer_query(app, 10, 12)
    await fun.on_quiz_answer(cast(CallbackQuery, wrong), app)
    assert "Мимо" in wrong.answer.await_args.args[0]
    retry = answer_query(app, 10, 11)
    await fun.on_quiz_answer(cast(CallbackQuery, retry), app)
    assert "уже отвечал" in retry.answer.await_args.args[0]
    right = answer_query(app, 12, 11)
    await fun.on_quiz_answer(cast(CallbackQuery, right), app)
    assert "Правильно" in right.answer.await_args.args[0]
    right.message.edit_text.assert_awaited_once()
    late = answer_query(app, 13, 11)
    await fun.on_quiz_answer(cast(CallbackQuery, late), app)
    assert "закончилась" in late.answer.await_args.args[0]
    assert [(r.user_id, r.value) for r in await app.db.counter_top(CHAT, fun.QUIZ_KEY)] == [(12, 1)]
