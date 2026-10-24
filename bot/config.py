import re
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split(value: Any) -> list[str] | Any:
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    allowed_chat_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    admin_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    trigger_words: Annotated[tuple[str, ...], NoDecode] = ("сглыпа",)

    db_path: Path = Path("data/sglypa.db")
    max_messages_per_chat: int = Field(10_000, ge=100)
    markov_order: int = Field(2, ge=1, le=4)
    default_reply_chance: int = Field(40, ge=0, le=100)
    tag_chance: int = Field(60, ge=0, le=100)
    ping_chance: int = Field(12, ge=0, le=100)
    revive_after_hours: float = Field(4.0, ge=0)
    quiet_hours: str = "1-10"
    timezone: str = "Europe/Moscow"
    min_message_length: int = Field(2, ge=1)
    max_message_length: int = Field(1000, ge=10)

    command_cooldown: float = Field(3.0, ge=0)
    reply_cooldown: float = Field(2.0, ge=0)
    all_cooldown: float = Field(300.0, ge=0)
    log_level: str = "INFO"

    @field_validator("allowed_chat_ids", "admin_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: Any) -> Any:
        return _split(value)

    @field_validator("quiet_hours")
    @classmethod
    def _check_quiet(cls, value: str) -> str:
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", value.strip())
        if not m or int(m[1]) > 23 or int(m[2]) > 23:
            raise ValueError("QUIET_HOURS must look like 1-10 (hours 0..23)")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("trigger_words", mode="before")
    @classmethod
    def _parse_words(cls, value: Any) -> Any:
        parts = _split(value)
        return tuple(p.lower() for p in parts) if isinstance(parts, list) else parts
