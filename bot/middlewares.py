import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Chat, Message, TelegramObject, User

from bot.config import Settings
from bot.db import Database
from bot.utils import GROUP_TYPES, Cooldown

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class WhitelistMiddleware(BaseMiddleware):
    """Drops every update that is not from an allowed group (or an admin's DM) and leaves foreign chats."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        settings: Settings = data["settings"]
        chat: Chat | None = data.get("event_chat")
        user: User | None = data.get("event_from_user")
        if chat is None:
            return None
        if chat.type == "private":
            if user is not None and user.id in settings.admin_ids:
                return await handler(event, data)
            return None
        if chat.id in settings.allowed_chat_ids:
            return await handler(event, data)
        log.warning("Foreign chat %s (%r): leaving", chat.id, chat.title)
        bot: Bot = data["bot"]
        with suppress(TelegramAPIError):
            await bot.leave_chat(chat.id)
        return None


class TrackUsersMiddleware(BaseMiddleware):
    """Remembers everyone who writes, so /all and @username lookups work (Bot API can't list members)."""

    async def __call__(self, handler: Handler, event: Message, data: dict[str, Any]) -> Any:
        user = event.from_user
        if user is not None and not user.is_bot and event.chat.type in GROUP_TYPES:
            db: Database = data["db"]
            await db.upsert_user(event.chat.id, user.id, user.full_name, user.username)
        return await handler(event, data)


class CommandCooldownMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._cooldown = Cooldown()

    async def __call__(self, handler: Handler, event: Message, data: dict[str, Any]) -> Any:
        settings: Settings = data["settings"]
        key = (event.chat.id, event.from_user.id if event.from_user else 0)
        if not self._cooldown.ready(key, settings.command_cooldown):
            return None
        return await handler(event, data)
