import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Chat, Message, TelegramObject, User

from bot import achievements
from bot.app import App
from bot.utils import GROUP_TYPES

log = logging.getLogger(__name__)

type Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class WhitelistMiddleware(BaseMiddleware):
    """Only our groups and admins' DMs get through. From any other group the bot just leaves."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        app: App = data["app"]
        chat: Chat | None = data.get("event_chat")
        user: User | None = data.get("event_from_user")
        if chat is None:
            return None
        if chat.type == "private":
            if user is not None and user.id in app.settings.admin_ids:
                return await handler(event, data)
            return None
        if chat.id in app.settings.allowed_chat_ids:
            return await handler(event, data)
        log.warning("Foreign chat %s (%r): leaving", chat.id, chat.title)
        with suppress(TelegramAPIError):
            await app.bot.leave_chat(chat.id)
        return None


class TrackUsersMiddleware(BaseMiddleware):
    # bots can't get the member list, so /all only knows people who wrote something

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message) and event.chat.type in GROUP_TYPES:
            user = event.from_user
            if user is not None and not user.is_bot:
                app: App = data["app"]
                seen = await app.db.upsert_user(event.chat.id, user.id, user.full_name, user.username)
                if seen is not None:
                    away = event.date.timestamp() - seen
                    await achievements.on_return(app, event.chat.id, user.id, user.full_name, away)
        return await handler(event, data)


class CommandCooldownMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message):
            app: App = data["app"]
            user_id = event.from_user.id if event.from_user else 0
            if not app.cooldowns.command.ready((event.chat.id, user_id)):
                return None
        return await handler(event, data)
