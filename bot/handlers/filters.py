from aiogram import F
from aiogram.filters import Filter
from aiogram.types import Message

from bot.app import App
from bot.utils import GROUP_TYPES

IN_GROUP = F.chat.type.in_(GROUP_TYPES)


class IsAdmin(Filter):
    async def __call__(self, message: Message, app: App) -> bool:
        return message.from_user is not None and message.from_user.id in app.settings.admin_ids
