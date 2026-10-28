from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from aiogram.filters import CommandObject
from aiogram.types import Message

from bot.app import App
from bot.handlers import admin, commands
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


async def test_forgetme(app: App) -> None:
    await app.db.add_message(CHAT, 10, "секрет", keep=100)
    message = fake_message(user_id=10)
    await commands.cmd_forgetme(cast(Message, message), app)
    assert await app.db.texts(CHAT) == []
    assert "Забыл 1" in said(message)


async def test_toad_is_sent_and_remembered(app: App) -> None:
    await app.db.add_toad_memes([("photo", "frogmemes", f"https://x/{i}.jpg") for i in range(400)])
    app.toads._last_refill = 1e18
    message = fake_message()
    message.answer_photo.return_value = SimpleNamespace(
        message_id=55, photo=[SimpleNamespace(file_id="TG_FILE")], animation=None, sticker=None
    )
    await commands.cmd_toad(cast(Message, message), command("жаба"), app)
    call = message.answer_photo.await_args
    assert call is not None and str(call.args[0]).startswith("https://x/")
    assert "жаба дня" in call.kwargs["caption"] and "Сила:" in call.kwargs["caption"]

    again = fake_message()
    again.answer_photo.return_value = SimpleNamespace(message_id=56, photo=None, animation=None, sticker=None)
    await commands.cmd_toad(cast(Message, again), command("жаба"), app)
    assert again.answer_photo.await_args is not None and again.answer_photo.await_args.args[0] == "TG_FILE"


async def test_toad_add_needs_a_picture(app: App) -> None:
    message = fake_message()
    await commands.cmd_toad(cast(Message, message), command("жаба", "добавь"), app)
    assert "Ответь" in said(message)
    replied = SimpleNamespace(
        photo=None, animation=None, sticker=SimpleNamespace(file_unique_id="u", file_id="F")
    )
    message = fake_message()
    message.reply_to_message = replied
    await commands.cmd_toad(cast(Message, message), command("жаба", "добавь"), app)
    assert "теперь их 1" in said(message)


async def test_not_toad_bans_meme_and_frees_the_day(app: App) -> None:
    await app.db.add_toad_memes([("photo", "frogmemes", f"https://x/{i}.jpg") for i in range(400)])
    app.toads._last_refill = 1e18
    message = fake_message()
    message.answer_photo.return_value = SimpleNamespace(
        message_id=55, photo=[SimpleNamespace(file_id="F")], animation=None, sticker=None
    )
    await commands.cmd_toad(cast(Message, message), command("жаба"), app)
    call = message.answer_photo.await_args
    assert call is not None
    url = str(call.args[0])

    vote = fake_message()
    vote.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(id=app.me.id), message_id=55)
    await commands.cmd_not_toad(cast(Message, vote), app)
    assert "Выкинул" in said(vote)
    app.bot.delete_message.assert_awaited_once_with(CHAT, 55)  # type: ignore[attr-defined]
    assert await app.db.add_toad_memes([("photo", "frogmemes", url)]) == 0
    assert await app.db.toad_meme_count() == 399


async def test_not_toad_needs_a_reply_to_the_bot(app: App) -> None:
    message = fake_message()
    await commands.cmd_not_toad(cast(Message, message), app)
    assert "Ответь" in said(message)
    message = fake_message()
    message.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(id=app.me.id), message_id=999)
    await commands.cmd_not_toad(cast(Message, message), app)
    assert "Не нашёл" in said(message)
