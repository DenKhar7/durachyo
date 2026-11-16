from aiogram.types import Message

from bot.db import KnownUser


def target_from_message(message: Message) -> KnownUser | None:
    for entity in message.entities or ():
        if entity.type == "text_mention" and entity.user and not entity.user.is_bot:
            u = entity.user
            return KnownUser(u.id, u.full_name, u.username)
    replied = message.reply_to_message
    if replied and replied.from_user and not replied.from_user.is_bot and replied.forum_topic_created is None:
        u = replied.from_user
        return KnownUser(u.id, u.full_name, u.username)
    return None
