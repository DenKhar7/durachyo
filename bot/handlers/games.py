import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import achievements
from bot.app import App
from bot.db import Duelist, KnownUser
from bot.duel import HOT_STREAK, fight, fight_line
from bot.handlers.filters import IN_GROUP
from bot.handlers.targets import target_from_message
from bot.middlewares import CommandCooldownMiddleware
from bot.utils import mention

router = Router(name="games")
router.message.filter(IN_GROUP)
router.message.middleware(CommandCooldownMiddleware())

RANDOM_TRIES = 5
TOP_SIZE = 10


@router.message(Command("дуэль", "duel", "пизда", "д"))
async def cmd_duel(message: Message, command: CommandObject, app: App) -> None:
    """/дуэль @vasya or as a reply - fight him. Without anyone - a random person from the chat."""
    author = message.from_user
    if author is None:
        return
    chat_id = message.chat.id
    username = next((a.removeprefix("@") for a in (command.args or "").split() if a.startswith("@")), None)
    if username:
        opponent = await app.db.find_user_by_username(chat_id, username)
        if opponent is None:
            await message.reply(f"Кто такой @{html.escape(username)}? Он тут ничего не писал.")
            return
    else:
        opponent = target_from_message(message) or await _random_opponent(app, chat_id, author.id)
    if opponent is None:
        await message.reply("Не с кем драться. Пусть кто-нибудь сначала напишет в чат.")
        return
    if opponent.user_id == author.id:
        await message.reply("Драться с собой - это к психологу.")
        return
    if not app.cooldowns.duel.ready(chat_id):
        await message.reply("Хватит махаться, отдохните минуту.")
        return

    result = fight(app.rng)
    a_won = result.a_won
    winner = None if a_won is None else (author.id if a_won else opponent.user_id)
    await app.db.record_duel(chat_id, winner, a=author.id, b=opponent.user_id)
    a = await app.db.duelist(chat_id, author.id)
    b = await app.db.duelist(chat_id, opponent.user_id)
    a_name, b_name = html.escape(author.full_name), html.escape(opponent.full_name)

    header = (
        f"⚔️ {mention(author.id, author.full_name)} 🎲{result.roll_a}  vs  "
        f"{mention(opponent.user_id, opponent.full_name)} 🎲{result.roll_b}"
    )
    lines = [
        header,
        "",
        fight_line(result, f"<b>{a_name}</b>", f"<b>{b_name}</b>", app.rng),
        "",
        f"{a_name}: {_score(a)}  ·  {b_name}: {_score(b)}",
    ]
    hot = a if winner == author.id else b if winner is not None else None
    if hot and hot.streak >= HOT_STREAK:
        lines.append(f"🔥 {html.escape(hot.name or 'безымянный')} на серии из {hot.streak}")
    await message.answer("\n".join(lines))
    await achievements.after_duel(app, chat_id, a, name=author.full_name, roll=result.roll_a)
    await achievements.after_duel(app, chat_id, b, name=opponent.full_name, roll=result.roll_b)


@router.message(Command("ачивки", "ачивка", "ach", "achievements"))
async def cmd_achievements(message: Message, app: App) -> None:
    """Your achievements. As a reply - that person's."""
    author = message.from_user
    target = target_from_message(message) or (
        KnownUser(author.id, author.full_name, author.username) if author else None
    )
    if target is None:
        return
    codes = await app.db.achievements(message.chat.id, target.user_id)
    await message.answer(achievements.card(target.full_name, codes))


@router.message(Command("топ", "top"))
async def cmd_top(message: Message, app: App) -> None:
    top = await app.db.duel_top(message.chat.id, TOP_SIZE)
    if not top:
        await message.reply("Ещё никто не дрался. /дуэль")
        return
    rows = [
        f"{place}. {html.escape(d.name or 'безымянный')} - {_score(d)} (лучшая серия {d.best_streak})"
        for place, d in enumerate(top, 1)
    ]
    await message.answer("🏆 <b>Топ дуэлянтов</b>\n" + "\n".join(rows))


def _score(d: Duelist) -> str:
    return f"{d.wins}-{d.losses}"


async def _random_opponent(app: App, chat_id: int, author_id: int) -> KnownUser | None:
    for _ in range(RANDOM_TRIES):
        user = await app.db.random_user(chat_id)
        if user and user.user_id != author_id:
            return user
    return None
