from datetime import UTC, datetime
from typing import Any

from aiogram.types import Message

CHAT = -100
BOT_ID = 1
BOT_USERNAME = "sglyper_bot"


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make_message(text: str, *, user_id: int = 10, name: str = "Вася", **extra: Any) -> Message:
    return Message.model_validate(
        {
            "message_id": 1,
            "date": datetime.now(UTC),
            "chat": {"id": CHAT, "type": "supergroup", "title": "чат"},
            "from": {"id": user_id, "is_bot": False, "first_name": name},
            "text": text,
            **extra,
        }
    )
