import re
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    ping_chance: int = Field(6, ge=0, le=100)
    called_chance: int = Field(80, ge=0, le=100)
    reaction_chance: int = Field(5, ge=0, le=100)
    nick_chance: int = Field(50, ge=0, le=100)
    catchphrases: Annotated[tuple[str, ...], NoDecode] = ("normalno", "normalno davai")
    revive_after_hours: float = Field(4.0, ge=0)
    quiet_hours: str = "1-10"
    timezone: str = "Europe/Moscow"
    min_message_length: int = Field(2, ge=1)
    max_message_length: int = Field(1000, ge=10)

    pinterest_app_id: str = ""
    pinterest_app_secret: SecretStr = SecretStr("")
    pinterest_refresh_token: SecretStr = SecretStr("")
    pinterest_board_id: str = Field("", pattern=r"^\d*$")  # numeric, goes into the API url

    command_cooldown: float = Field(3.0, ge=0)
    reply_cooldown: float = Field(2.0, ge=0)
    all_cooldown: float = Field(300.0, ge=0)
    duels_per_minute: int = Field(5, ge=1)
    log_level: str = "INFO"

    @property
    def pinterest_ready(self) -> bool:
        return bool(
            self.pinterest_app_id
            and self.pinterest_app_secret.get_secret_value()
            and self.pinterest_refresh_token.get_secret_value()
            and self.pinterest_board_id
        )

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
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown TIMEZONE {value!r}") from exc
        return value

    @field_validator("catchphrases", mode="before")
    @classmethod
    def _parse_phrases(cls, value: Any) -> Any:
        parts = _split(value)
        return tuple(parts) if isinstance(parts, list) else parts

    @field_validator("trigger_words", mode="before")
    @classmethod
    def _parse_words(cls, value: Any) -> Any:
        parts = _split(value)
        return tuple(p.lower() for p in parts) if isinstance(parts, list) else parts
