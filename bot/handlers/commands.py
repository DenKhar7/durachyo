import html
import logging

from aiogram import Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message

from bot.app import App
from bot.handlers.filters import IN_GROUP
from bot.handlers.targets import target_from_message
from bot.media import best_photo, chat_demotivator
from bot.middlewares import CommandCooldownMiddleware
from bot.utils import chunks, mention

log = logging.getLogger(__name__)

router = Router(name="commands")
router.message.middleware(CommandCooldownMiddleware())

MENTIONS_PER_MESSAGE = 5
MAX_CAPTION = 120

HELP = (
    "<b>Сглыпа 2.0</b> - запоминаю, что вы пишете, и использую против вас. "
    "Сам решаю, когда влезть, кого подколоть и когда разбудить заглохший чат.\n\n"
    "Позвать: ответь мне, упомяни или напиши «сглыпа».\n\n"
    "/sglyp [@user|слово] - бред по чату, в стиле человека или со слова\n"
    "/demotiv или /демотив [текст] - демотиватор (реплаем на фото - из него)\n"
    "/дуэль, /д, /пизда [@user] - подраться (реплаем - с ним, без никого - со случайным)\n"
    "/топ - лучшие дуэлянты\n"
    "/стата - твоя статистика дуэлей (реплаем - чужая)\n"
    "/ачивки - твои ачивки (реплаем - чужие)\n"
    "/ктосказал - угадай автора старой фразы (/ктосказал топ - лучшие)\n"
    "/лох - лох дня (/лох топ - рейтинг)\n"
    "/гороскоп - твой гороскоп на сегодня\n"
    "@бот кто насрал? - узнать правду\n"
    "/all - пингануть всех\n"
    "/forgetme - стереть мои сообщения из памяти\n\n"
    "Админ: /chance N (болтливость), /tag Имя ярлык, /untag Имя, /tags"
)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("sglyp"), IN_GROUP)
async def cmd_sglyp(message: Message, command: CommandObject, app: App) -> None:
    """/sglyp - chat nonsense. With @vasya or as a reply - in his style. With a word - starts from it."""
    args = (command.args or "").split()
    username = next((a.removeprefix("@") for a in args if a.startswith("@")), None)
    seed = next((a for a in args if not a.startswith("@")), None)
    chat_id = message.chat.id
    if username:
        target = await app.db.find_user_by_username(chat_id, username)
        if target is None:
            await message.reply(f"Кто такой @{html.escape(username)}? Он тут ничего не писал.")
            return
    else:
        target = target_from_message(message)

    chain = await (app.chains.for_user(chat_id, target.user_id) if target else app.chains.get(chat_id))
    text = (chain.generate(seed, rng=app.rng) if seed else None) or chain.generate(rng=app.rng)
    if not text:
        await message.reply("Мало данных. Болтайте больше, я учусь.")
        return
    body = html.escape(text)
    if target:
        body = f"Как сказал бы {mention(target.user_id, target.full_name)}: «{body}»"
    await message.answer(body)


@router.message(Command("demotiv", "демотив", "dem", "дем"), IN_GROUP)
async def cmd_demotiv(message: Message, command: CommandObject, app: App) -> None:
    """As a reply to a photo - uses that photo. Text after the command becomes the caption."""
    replied = message.reply_to_message
    photo = best_photo(replied.photo if replied else None) or best_photo(message.photo)
    await app.bot.send_chat_action(
        message.chat.id, ChatAction.UPLOAD_PHOTO, message_thread_id=message.message_thread_id
    )
    image = await chat_demotivator(
        app.bot,
        app.db,
        await app.chains.get(message.chat.id),
        message.chat.id,
        rng=app.rng,
        file_id=photo.file_id if photo else None,
        seed_text=(replied.text or replied.caption or "") if replied else "",
        title=(command.args or "").strip()[:MAX_CAPTION] or None,
    )
    if image is None:
        await message.reply("Нет картинок. Скиньте фото в чат, я запомню.")
        return
    await message.answer_photo(BufferedInputFile(image, "demotivator.jpg"))


@router.message(Command("all"), IN_GROUP)
async def cmd_all(message: Message, app: App) -> None:
    if not app.cooldowns.everyone.ready(message.chat.id):
        await message.reply("Не спамь. Общий сбор раз в несколько минут.")
        return
    caller = message.from_user.id if message.from_user else 0
    users = [u for u in await app.db.users(message.chat.id) if u.user_id != caller]
    if not users:
        await message.reply("Я пока никого не знаю.")
        return
    for i, part in enumerate(chunks(users, MENTIONS_PER_MESSAGE)):
        prefix = "Общий сбор! " if i == 0 else ""
        await message.answer(prefix + " ".join(mention(u.user_id, u.full_name) for u in part))


@router.message(Command("forgetme"), IN_GROUP)
async def cmd_forgetme(message: Message, app: App) -> None:
    if message.from_user is None:
        return
    deleted = await app.db.forget_user(message.chat.id, message.from_user.id)
    app.chains.invalidate(message.chat.id)
    await message.reply(f"Забыл {deleted} твоих фраз. Но осадочек остался.")
