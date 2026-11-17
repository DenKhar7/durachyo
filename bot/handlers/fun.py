import asyncio
import html
from contextlib import suppress
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import daily
from bot.app import App
from bot.daily import Quiz
from bot.db import KnownUser
from bot.handlers.filters import IN_GROUP
from bot.middlewares import CommandCooldownMiddleware
from bot.phrases import pick_phrase
from bot.utils import mention
from bot.wordplay import rare_words

router = Router(name="fun")
router.message.filter(IN_GROUP)
router.message.middleware(CommandCooldownMiddleware())

DRAMA_PAUSE = 1.5
QUIZ_OPTIONS = 3
MAX_OPEN_QUIZZES = 50
TOP_SIZE = 10
TOP_WORDS = frozenset({"топ", "top"})
LOSER_KEY = "loser_days"
QUIZ_KEY = "quiz_points"


def _today(app: App) -> date:
    return datetime.now(ZoneInfo(app.settings.timezone)).date()


def _name(user: KnownUser | None, user_id: int) -> str:
    return mention(user_id, user.full_name if user else None)


async def _top(message: Message, app: App, key: str, title: str) -> None:
    rows = await app.db.counter_top(message.chat.id, key, TOP_SIZE)
    if not rows:
        await message.reply("Пока пусто.")
        return
    lines = [f"{i}. {html.escape(r.name or 'безымянный')} - {r.value}" for i, r in enumerate(rows, 1)]
    await message.answer(f"<b>{title}</b>\n" + "\n".join(lines))


# ---------- лох дня ----------


@router.message(Command("лох", "loser"))
async def cmd_loser(message: Message, command: CommandObject, app: App) -> None:
    if (command.args or "").strip().lower() in TOP_WORDS:
        await _top(message, app, LOSER_KEY, "🤡 Чаще всех был лохом")
        return
    chat_id, today = message.chat.id, _today(app)
    stored = await app.db.daily_pick(chat_id, today, "loser")
    if stored is not None:
        user_id = int(stored)
        user = await app.db.get_user(chat_id, user_id)
        await message.reply(f"Лошара уже выбран: {_name(user, user_id)}. Новый завтра :3")
        return
    users = await app.db.users(chat_id)
    if not users:
        await message.reply("Чё")
        return
    loser = app.rng.choice(users)
    stored = await app.db.set_daily_pick(chat_id, today, "loser", str(loser.user_id))
    if int(stored) != loser.user_id:  # someone was faster
        return
    await app.db.bump_counter(chat_id, loser.user_id, LOSER_KEY)
    for line in daily.LOSER_DRAMA:
        await message.answer(line)
        await asyncio.sleep(DRAMA_PAUSE)
    name = mention(loser.user_id, loser.full_name)
    await message.answer(app.rng.choice(daily.LOSER_LINES).format(name=name))


# ---------- гороскоп ----------


@router.message(Command("гороскоп", "horoscope"))
async def cmd_horoscope(message: Message, app: App) -> None:
    user = message.from_user
    if user is None:
        return
    chat_id, today = message.chat.id, _today(app)
    kind = f"horo:{user.id}"
    text = await app.db.daily_pick(chat_id, today, kind)
    if text is None:
        text = await app.db.set_daily_pick(
            chat_id, today, kind, await _make_horoscope(app, chat_id, user.id, today)
        )
    await message.reply(f"🔮 Гороскоп для {mention(user.id, user.full_name)}\n{text}")


async def _make_horoscope(app: App, chat_id: int, user_id: int, today: date) -> str:
    rng = daily.day_rng("horo", chat_id, user_id, today)
    chain = await app.chains.get(chat_id)
    lines = [f"Знак: <b>{daily.sign_of(user_id)}</b>"]
    phrase = await pick_phrase(app.db, chat_id) or chain.generate(max_words=8, rng=rng)
    if phrase:
        lines.append(rng.choice(daily.FORECASTS).format(phrase=html.escape(phrase)))
    others = [u for u in await app.db.users(chat_id) if u.user_id != user_id]
    if others:
        enemy = rng.choice(others)
        lines.append(f"Опасайся: {html.escape(enemy.full_name)}")
    words = rare_words(" ".join(chain.vocabulary()[:300]), chain, rng, n=1)
    if words:
        lines.append(f"Счастливое слово: {html.escape(words[0])}")
    lines.append(f"Удача: {rng.randint(0, 100)}%")
    return "\n".join(lines)


# ---------- кто это сказал ----------


@router.message(Command("ктосказал", "угадай", "quiz"))
async def cmd_quiz(message: Message, command: CommandObject, app: App) -> None:
    if (command.args or "").strip().lower() in TOP_WORDS:
        await _top(message, app, QUIZ_KEY, "🕵 Лучшие дэутективы")
        return
    chat_id = message.chat.id
    quote = await app.db.random_quote(chat_id)
    users = await app.db.users(chat_id)
    others = [u for u in users if quote and u.user_id != quote.user_id]
    if quote is None or len(others) < QUIZ_OPTIONS - 1:
        await message.reply("Чё")
        return
    options = [KnownUser(quote.user_id, quote.name), *app.rng.sample(others, QUIZ_OPTIONS - 1)]
    app.rng.shuffle(options)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=u.full_name[:30], callback_data=f"quiz:{u.user_id}")] for u in options
        ]
    )
    sent = await message.answer(f"🕵 Кто это сказал, а?\n\n«{html.escape(quote.text)}»", reply_markup=keyboard)
    if len(app.quizzes) >= MAX_OPEN_QUIZZES:
        app.quizzes.pop(next(iter(app.quizzes)))
    app.quizzes[(chat_id, sent.message_id)] = Quiz(quote.user_id, quote.name, quote.text)


@router.callback_query(F.data.startswith("quiz:"))
async def on_quiz_answer(query: CallbackQuery, app: App) -> None:
    message = query.message
    if not isinstance(message, Message) or not query.data:
        await query.answer()
        return
    key = (message.chat.id, message.message_id)
    quiz = app.quizzes.get(key)
    user = query.from_user
    if quiz is None:
        await query.answer("Эта викторина уже закончилась")
        return
    if user.id == quiz.author_id:
        await query.answer("НЕ ПОДСКАЗЫВАЙ", show_alert=True)
        return
    if user.id in quiz.guessed:
        await query.answer("Ты уже ответил")
        return
    quiz.guessed.add(user.id)
    if int(query.data.removeprefix("quiz:")) != quiz.author_id:
        await query.answer("Мимо 🤡", show_alert=True)
        return
    app.quizzes.pop(key, None)
    points = await app.db.bump_counter(message.chat.id, user.id, QUIZ_KEY)
    await query.answer("ВЕРНО!")
    with suppress(TelegramAPIError):
        await message.edit_text(
            f"🕵 «{html.escape(quiz.phrase)}»\n\n"
            f"Это сказал {mention(quiz.author_id, quiz.author_name)}.\n"
            f"Первым угадал {mention(user.id, user.full_name)} (+1, всего {points})",
            reply_markup=None,
        )
