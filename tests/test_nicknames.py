import random

from bot.db import Tag
from bot.nicknames import NickHit, find_nick, find_tag, nick_line

TAGS = [Tag("зигор", "Зигор", "педофайл"), Tag("егор", "Егор", "педофайл")]


def nick(text: str) -> NickHit:
    hit = find_nick(text)
    assert hit is not None, text
    return hit


def test_nicknames_match_forms_not_lookalikes() -> None:
    assert nick("где Маша").name == "Маша"
    assert nick("машке передай").name == "Маша"
    assert nick("скажи Лесону").name == "Лесон"
    assert nick("дениска опять").name == "Денис"
    assert nick("ЕГОРУ привет").name == "Егор"
    assert nick("Зигор!").name == "Зигор"
    for text in ("машина сломалась", "пригорело", "денег нет"):
        assert find_nick(text) is None, text


def test_zigor_keeps_the_written_name_without_ending() -> None:
    assert nick("зигагор тут").name == "Зигагор"
    assert nick("Зигагору привет").name == "Зигагор"
    assert nick("зигогора нет").name == "Зигогор"


def test_nick_lines() -> None:
    rng = random.Random(0)
    assert nick_line(nick("Маша"), rng) in {"Маша - свинья", "Маша - псина"}
    assert nick_line(nick("егор"), rng) in {"Егор = пдфайл", "Егор = лоликонщик", "Егор = лоли"}
    assert nick_line(nick("Зигору"), rng) in {"Зигор = пдфайл", "Зигор = лоликонщик", "Зигор = лоли"}


def test_find_tag_matches_name_and_endings() -> None:
    for text, name in [("ну Зигор опять", "Зигор"), ("спроси у Егора!", "Егор"), ("ЕГОРУ привет", "Егор")]:
        tag = find_tag(text, TAGS)
        assert tag is not None and tag.name == name


def test_find_tag_ignores_unrelated_words() -> None:
    for text in ("пригорело", "егоркинский район", ""):
        assert find_tag(text, TAGS) is None
