from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import TelegramObject

from bot.app import App
from bot.handlers.filters import IsAdmin
from bot.middlewares import CommandCooldownMiddleware, TrackUsersMiddleware, WhitelistMiddleware
from tests.helpers import CHAT, make_message

ADMIN = 42


def data(app: App, chat_id: int, chat_type: str = "supergroup", user_id: int = 10) -> dict[str, Any]:
    return {
        "app": app,
        "event_chat": SimpleNamespace(id=chat_id, type=chat_type, title="t"),
        "event_from_user": SimpleNamespace(id=user_id),
    }


async def test_whitelist_passes_allowed_group_and_leaves_foreign_one(app: App, bot: AsyncMock) -> None:
    handler = AsyncMock(return_value="ok")
    event = TelegramObject()
    middleware = WhitelistMiddleware()
    assert await middleware(handler, event, data(app, CHAT)) == "ok"
    assert await middleware(handler, event, data(app, -999)) is None
    bot.leave_chat.assert_awaited_once_with(-999)


async def test_whitelist_lets_only_admins_into_dms(app: App) -> None:
    app.settings = app.settings.model_copy(update={"admin_ids": frozenset({ADMIN})})
    handler = AsyncMock(return_value="ok")
    middleware = WhitelistMiddleware()
    assert await middleware(handler, TelegramObject(), data(app, ADMIN, "private", ADMIN)) == "ok"
    assert await middleware(handler, TelegramObject(), data(app, 10, "private", 10)) is None


async def test_track_users_remembers_authors(app: App) -> None:
    handler = AsyncMock()
    await TrackUsersMiddleware()(handler, make_message("привет"), {"app": app})
    users = await app.db.users(CHAT)
    assert [u.full_name for u in users] == ["Вася"]
    handler.assert_awaited_once()


async def test_command_cooldown_blocks_flood(app: App) -> None:
    handler = AsyncMock(return_value="ok")
    middleware = CommandCooldownMiddleware()
    message = make_message("/sglyp")
    assert await middleware(handler, message, {"app": app}) == "ok"
    assert await middleware(handler, message, {"app": app}) is None


async def test_is_admin(app: App) -> None:
    app.settings = app.settings.model_copy(update={"admin_ids": frozenset({ADMIN})})
    assert await IsAdmin()(make_message("/chance", user_id=ADMIN), app)
    assert not await IsAdmin()(make_message("/chance", user_id=10), app)
