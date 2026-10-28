"""Commands for everyone in the group."""

import html
import logging
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message

from bot.app import App
from bot.db import KnownUser, ToadMeme
from bot.handlers.filters import IN_GROUP
from bot.media import best_photo, chat_demotivator
from bot.middlewares import CommandCooldownMiddleware
from bot.toad import toad_of_the_day
from bot.utils import chunks, mention

log = logging.getLogger(__name__)

router = Router(name="commands")
router.message.middleware(CommandCooldownMiddleware())

MENTIONS_PER_MESSAGE = 5
MAX_CAPTION = 120
TOAD_TRIES = 3
ADD_WORDS = frozenset({"добавь", "добавить", "add", "+"})

HELP = (
    "<b>Сглыпа 2.0</b> - запоминаю, что вы пишете, и использую против вас. "
    "Сам решаю, когда влезть, кого подколоть и когда разбудить заглохший чат.\n\n"
    "Позвать: ответь мне, упомяни или напиши «сглыпа».\n\n"
    "/sglyp [@user|слово] - бред по чату, в стиле человека или со слова\n"
    "/demotiv или /демотив [текст] - демотиватор (реплаем на фото - из него)\n"
    "/жаба - твоя жаба дня (реплаем - чужая)\n"
    "/жаба добавь - реплаем на картинку: пополнить жабью коллекцию\n"
    "/нежаба - реплаем на жабу дня: выкинуть, если это не жаба\n"
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
    """Nonsense from the chat. With @user or as a reply: in that person's style. With a word: from it."""
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
        target = _target_from_message(message)

    chain = await (app.chains.for_user(chat_id, target.user_id) if target else app.chains.get(chat_id))
    text = (chain.generate(seed, rng=app.rng) if seed else None) or chain.generate(rng=app.rng)
    if not text:
        await message.reply("Мало данных. Болтайте больше, я учусь.")
        return
    body = html.escape(text)
    if target:
        body = f"Как сказал бы {mention(target.user_id, target.full_name)}: «{body}»"
    await message.answer(body)


def _target_from_message(message: Message) -> KnownUser | None:
    """The person picked by a text mention (users without @username) or by replying to them."""
    for entity in message.entities or ():
        if entity.type == "text_mention" and entity.user and not entity.user.is_bot:
            u = entity.user
            return KnownUser(u.id, u.full_name, u.username)
    replied = message.reply_to_message
    if replied and replied.from_user and not replied.from_user.is_bot and replied.forum_topic_created is None:
        u = replied.from_user
        return KnownUser(u.id, u.full_name, u.username)
    return None


@router.message(Command("demotiv", "демотив", "dem", "дем"), IN_GROUP)
async def cmd_demotiv(message: Message, command: CommandObject, app: App) -> None:
    """Demotivator. As a reply to a photo: from that photo. With text: that text as the caption."""
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


@router.message(Command("жаба", "zhaba", "toad"), IN_GROUP)
async def cmd_toad(message: Message, command: CommandObject, app: App) -> None:
    """Жаба дня: a toad meme, one per person per day. As a reply: that person's toad.
    "/жаба добавь" as a reply to a picture, gif or sticker adds it to the chat's collection."""
    if (command.args or "").strip().lower() in ADD_WORDS:
        await _add_toad(message, app)
        return
    author = message.from_user
    target = _target_from_message(message) or (
        KnownUser(author.id, author.full_name, author.username) if author else None
    )
    if target is None:
        return
    today = datetime.now(ZoneInfo(app.settings.timezone)).date()
    toad = toad_of_the_day(message.chat.id, target.user_id, today)
    caption = (
        f"🐸 {mention(target.user_id, target.full_name)}, жаба дня:\n"
        f"<b>{html.escape(toad.name)}</b>\n"
        f"Редкость: {toad.rarity.name}\n"
        f"Сила: {toad.power}/100"
    )
    for _ in range(TOAD_TRIES):
        meme = await app.toads.pick(app.db, message.chat.id, target.user_id, today, app.rng)
        if meme is None:
            await message.reply("Жабы кончились. Скиньте свою и ответьте на неё «/жаба добавь».")
            return
        try:
            sent = await _send_toad(message, meme, caption)
        except TelegramBadRequest as exc:
            log.warning("toad meme %s is gone: %s", meme.id, exc)
            await app.db.drop_toad_meme(meme.id)
            continue
        for post in sent:
            await app.db.remember_toad_post(message.chat.id, post.message_id, meme.id, today)
        if file_id := _file_id(sent[0]):
            await app.db.set_toad_file_id(meme.id, file_id)
        return
    await message.reply("Жабы спят. Попробуй через минуту.")


async def _add_toad(message: Message, app: App) -> None:
    replied = message.reply_to_message
    media = _toad_media(replied) if replied else None
    if media is None:
        await message.reply("Ответь «/жаба добавь» на картинку, гифку или стикер с жабой.")
        return
    kind, uid, file_id = media
    added = await app.db.add_chat_toad(message.chat.id, kind, uid, file_id)
    total = await app.db.toad_meme_count(message.chat.id)
    await message.reply(f"Жаба в коллекции, теперь их {total}." if added else "Эта жаба уже есть.")


def _toad_media(message: Message) -> tuple[str, str, str] | None:
    if photo := best_photo(message.photo):
        return "photo", photo.file_unique_id, photo.file_id
    if message.animation:
        return "animation", message.animation.file_unique_id, message.animation.file_id
    if message.sticker:
        return "sticker", message.sticker.file_unique_id, message.sticker.file_id
    return None


async def _send_toad(message: Message, meme: ToadMeme, caption: str) -> list[Message]:
    """The toad post; a sticker can't carry a caption, so it goes as two messages."""
    media = meme.file_id or meme.url or ""
    if meme.kind == "sticker":
        return [await message.answer_sticker(media), await message.answer(caption)]
    if meme.kind == "animation":
        return [await message.answer_animation(media, caption=caption)]
    return [await message.answer_photo(media, caption=caption)]


def _file_id(sent: Message) -> str | None:
    if sent.photo:
        return sent.photo[-1].file_id
    if sent.animation:
        return sent.animation.file_id
    return sent.sticker.file_id if sent.sticker else None


@router.message(Command("нежаба", "nezhaba", "nottoad"), IN_GROUP)
async def cmd_not_toad(message: Message, app: App) -> None:
    """Reply to the bot's toad of the day: that meme is not a toad, never show it again."""
    replied = message.reply_to_message
    if replied is None or replied.from_user is None or replied.from_user.id != app.me.id:
        await message.reply("Ответь /нежаба на жабу дня, которую я прислал.")
        return
    meme = await app.db.toad_by_post(message.chat.id, replied.message_id)
    if meme is None:
        await message.reply("Не нашёл эту жабу. Она старая или уже выкинута.")
        return
    await app.db.ban_toad_meme(meme.id)
    with suppress(TelegramAPIError):
        await app.bot.delete_message(message.chat.id, replied.message_id)
    await message.reply("Выкинул, больше не выпадет. Хозяин жабы может взять новую: /жаба")


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
