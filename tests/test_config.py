import pytest
from pydantic import ValidationError

from bot.config import Settings


def test_lists_parsed_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "1:abc")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "-1001, -1002")
    monkeypatch.setenv("ADMIN_IDS", "42")
    monkeypatch.setenv("TRIGGER_WORDS", "Сглыпа, Бот")
    s = Settings(_env_file=None)
    assert s.allowed_chat_ids == frozenset({-1001, -1002})
    assert s.admin_ids == frozenset({42})
    assert s.trigger_words == ("сглыпа", "бот")
    assert "abc" not in repr(s)


def test_empty_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "1:abc")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "")
    assert Settings(_env_file=None).allowed_chat_ids == frozenset()


def test_bad_timezone_is_a_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "1:abc")
    with pytest.raises(ValidationError, match="TIMEZONE"):
        Settings(_env_file=None, timezone="Mars/Olympus")


def test_bad_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "1:abc")
    with pytest.raises(ValidationError, match="QUIET_HOURS"):
        Settings(_env_file=None, quiet_hours="ночью")
