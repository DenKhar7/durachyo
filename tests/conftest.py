import random
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram.types import User
from pydantic import SecretStr

from bot.app import App
from bot.config import Settings
from bot.db import Database
from tests.helpers import BOT_ID, BOT_USERNAME, CHAT


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = await Database.open(tmp_path / "test.db")
    yield database
    await database.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(bot_token=SecretStr("1:test"), allowed_chat_ids=frozenset({CHAT}), _env_file=None)


@pytest.fixture
def bot() -> AsyncMock:
    fake = AsyncMock()
    fake.send_message.return_value = SimpleNamespace(message_id=100)
    return fake


@pytest.fixture
def app(settings: Settings, bot: AsyncMock, db: Database) -> App:
    me = User(id=BOT_ID, is_bot=True, first_name="Сглыпа", username=BOT_USERNAME)
    app = App.create(settings, bot, db, me)
    app.rng = random.Random(0)
    return app
