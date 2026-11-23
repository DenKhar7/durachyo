from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from aiogram.filters import CommandObject
from aiogram.types import Message

from bot.app import App
from bot.handlers import admin, commands, games
from tests.helpers import CHAT


def fake_message(user_id: int = 10) -> AsyncMock:
    """Duck-typed Message: reply/answer are recorded instead of going to Telegram."""
    message = AsyncMock()
    message.chat = SimpleNamespace(id=CHAT, type="supergroup")
    message.from_user = SimpleNamespace(id=user_id, full_name="Вася", username="vasya", is_bot=False)
    message.entities = None
    message.reply_to_message = None
    return message


def command(name: str, args: str | None = None) -> CommandObject:
    return CommandObject(prefix="/", command=name, args=args)


def said(message: AsyncMock) -> str:
    call = message.reply.await_args or message.answer.await_args
    assert call is not None
    return str(call.args[0])


async def test_chance_shows_and_sets(app: App) -> None:
    message = fake_message()
    await admin.cmd_chance(cast(Message, message), command("chance"), app)
    assert "40%" in said(message)
    await admin.cmd_chance(cast(Message, message), command("chance", "25%"), app)
    assert await app.db.reply_chance(CHAT, 40) == 25


async def test_chance_rejects_garbage(app: App) -> None:
    for bad in ("много", "-5", "150"):
        message = fake_message()
        await admin.cmd_chance(cast(Message, message), command("chance", bad), app)
        assert "от 0 до 100" in said(message)
    assert await app.db.reply_chance(CHAT, 40) == 40


async def test_tag_untag_tags(app: App) -> None:
    await admin.cmd_tag(cast(Message, fake_message()), command("tag", "Зигор  главный   нуб"), app)
    message = fake_message()
    await admin.cmd_tags(cast(Message, message), app)
    assert said(message) == "Зигор - главный нуб"
    await admin.cmd_untag(cast(Message, fake_message()), command("untag", "зигор"), app)
    assert await app.db.tags(CHAT) == []


async def test_tag_escapes_html(app: App) -> None:
    message = fake_message()
    await admin.cmd_tag(cast(Message, message), command("tag", "Зигор <b>жирный</b>"), app)
    assert "<b>" not in said(message)


async def test_sglyp_speaks_from_chat_and_knows_unknown_users(app: App) -> None:
    for text in ["я пью пиво дома", "мы пьём пиво на улице"]:
        await app.db.add_message(CHAT, 10, text, keep=100)
    message = fake_message()
    await commands.cmd_sglyp(cast(Message, message), command("sglyp", "пиво"), app)
    assert "пиво" in said(message)
    message = fake_message()
    await commands.cmd_sglyp(cast(Message, message), command("sglyp", "@nobody"), app)
    assert "@nobody" in said(message)


async def test_all_pings_everyone_but_caller_and_has_cooldown(app: App) -> None:
    for user_id, name in [(10, "Вася"), (11, "Петя"), (12, "Маша")]:
        await app.db.upsert_user(CHAT, user_id, name, None)
    message = fake_message(user_id=10)
    await commands.cmd_all(cast(Message, message), app)
    text = said(message)
    assert "Петя" in text and "Маша" in text and "Вася" not in text
    again = fake_message()
    await commands.cmd_all(cast(Message, again), app)
    assert "Не спамь" in said(again)


async def test_duel_with_username_records_result(app: App) -> None:
    await app.db.upsert_user(CHAT, 11, "Петя", "petya")
    message = fake_message()
    await games.cmd_duel(cast(Message, message), command("дуэль", "@Petya"), app)
    text = said(message)
    assert "⚔️" in text and "Петя" in text and "Вася" in text and "🎲" in text
    assert "Встречи:" in text
    a, b = await app.db.duelist(CHAT, 10), await app.db.duelist(CHAT, 11)
    assert a.wins + a.losses == b.wins + b.losses <= 1


async def test_duel_random_opponent_self_and_nobody(app: App) -> None:
    message = fake_message()
    await games.cmd_duel(cast(Message, message), command("дуэль"), app)
    assert "Не с кем" in said(message)
    await app.db.upsert_user(CHAT, 10, "Вася", "vasya")
    message = fake_message()
    await games.cmd_duel(cast(Message, message), command("дуэль", "@vasya"), app)
    assert "психологу" in said(message)
    await app.db.upsert_user(CHAT, 12, "Маша", None)
    message = fake_message()
    await games.cmd_duel(cast(Message, message), command("дуэль"), app)
    assert "Маша" in said(message)


async def test_duel_limit_per_minute(app: App) -> None:
    await app.db.upsert_user(CHAT, 11, "Петя", "petya")
    for _ in range(5):
        await games.cmd_duel(cast(Message, fake_message()), command("дуэль", "@petya"), app)
    message = fake_message()
    await games.cmd_duel(cast(Message, message), command("дуэль", "@petya"), app)
    assert "отдохните" in said(message)


async def test_top(app: App) -> None:
    message = fake_message()
    await games.cmd_top(cast(Message, message), app)
    assert "никто не дрался" in said(message)
    await app.db.upsert_user(CHAT, 11, "Петя", None)
    await app.db.record_duel(CHAT, 11, a=10, b=11)
    message = fake_message()
    await games.cmd_top(cast(Message, message), app)
    assert "1. Петя - 1-0" in said(message)


async def test_stats(app: App) -> None:
    message = fake_message()
    await games.cmd_stats(cast(Message, message), app)
    assert "ни с кем не дрался" in said(message)
    await app.db.upsert_user(CHAT, 11, "Петя", None)
    await app.db.upsert_user(CHAT, 12, "Маша", None)
    for winner in (10, 10, 11):
        await app.db.record_duel(CHAT, winner, a=10, b=11)
    await app.db.record_duel(CHAT, 12, a=10, b=12)
    await app.db.record_duel(CHAT, None, a=12, b=10)
    message = fake_message()
    await games.cmd_stats(cast(Message, message), app)
    text = said(message)
    assert "Боёв: 5" in text and "побед 2, поражений 2, ничьих 1" in text and "Винрейт: 40%" in text
    assert "Чаще всего дрался с Петя (2:1)" in text
    assert (
        "Любимая груша: Петя (2:1)" in text and "Злой рок: Петя (2:1)" in text
    ) or "Злой рок: Маша (0:1)" in text
