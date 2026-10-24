import html

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database, KnownUser
from bot.middlewares import CommandCooldownMiddleware
from bot.utils import GROUP_TYPES, Cooldown, chunks, mention

router = Router(name="commands")
router.message.middleware(CommandCooldownMiddleware())

in_group = F.chat.type.in_(GROUP_TYPES)
_all_cooldown = Cooldown()
MENTIONS_PER_MESSAGE = 5

HELP = (
    "<b>Сглыпа 2.0</b> - запоминаю, что вы пишете, и использую против вас. "
    "Сам решаю, когда влезть, кого подколоть и когда разбудить заглохший чат.\n\n"
    "Позвать: ответь мне, упомяни или напиши «сглыпа».\n\n"
    "/sglyp [@user|слово] - бред по чату, в стиле человека или со слова\n"
    "/all - пингануть всех\n"
    "/forgetme - стереть мои сообщения из памяти\n\n"
    "Админ: /chance N (болтливость), /tag Имя ярлык, /untag Имя, /tags"
)



async def _resolve_target(message: Message, command: CommandObject, db: Database) -> tuple[KnownUser | None, bool]:
    """(target, ok). ok=False means an explicit @username was unknown and the user was told so."""
    for ent in message.entities or ():
        if ent.type == "text_mention" and ent.user and not ent.user.is_bot:
            return KnownUser(ent.user.id, ent.user.full_name, ent.user.username), True
    args = (command.args or "").split()
    if args and args[0].startswith("@"):
        user = await db.find_user_by_username(message.chat.id, args[0][1:])
        if user is None:
            await message.reply(f"Кто такой {html.escape(args[0])}? Он тут ничего не писал.")
            return None, False
        return user, True
    reply = message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot and reply.forum_topic_created is None:
        u = reply.from_user
        return KnownUser(u.id, u.full_name, u.username), True
    return None, True


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("sglyp"), in_group)
async def cmd_sglyp(message: Message, command: CommandObject, db: Database, chains: ChainStore) -> None:
    target, ok = await _resolve_target(message, command, db)
    if not ok:
        return
    seed = next((w for w in (command.args or "").split() if not w.startswith("@")), None)
    chain = await (chains.for_user(message.chat.id, target.user_id) if target else chains.get(message.chat.id))
    text = chain.generate(seed) if seed else None
    text = text or chain.generate()
    if not text:
        await message.reply("Мало данных. Болтайте больше, я учусь.")
        return
    body = html.escape(text)
    if target:
        body = f"Как сказал бы {mention(target.user_id, target.full_name)}: «{body}»"
    await message.answer(body)


@router.message(Command("all"), in_group)
async def cmd_all(message: Message, db: Database, settings: Settings) -> None:
    if not _all_cooldown.ready(message.chat.id, settings.all_cooldown):
        await message.reply("Не спамь. Общий сбор раз в несколько минут.")
        return
    caller = message.from_user.id if message.from_user else 0
    users = [u for u in await db.users(message.chat.id) if u.user_id != caller]
    if not users:
        await message.reply("Я пока никого не знаю.")
        return
    for i, part in enumerate(chunks(users, MENTIONS_PER_MESSAGE)):
        prefix = "Общий сбор! " if i == 0 else ""
        await message.answer(prefix + " ".join(mention(u.user_id, u.full_name) for u in part))


@router.message(Command("forgetme"), in_group)
async def cmd_forgetme(message: Message, db: Database, chains: ChainStore) -> None:
    if message.from_user is None:
        return
    deleted = await db.forget_user(message.chat.id, message.from_user.id)
    chains.invalidate(message.chat.id)
    await message.reply(f"Забыл {deleted} твоих фраз. Но осадочек остался.")
