from bot.db import Tag
from bot.responder import find_tag

TAGS = [Tag("зигор", "Зигор", "педофайл"), Tag("егор", "Егор", "педофайл")]


def test_find_tag_matches_name_and_endings():
    assert find_tag("ну Зигор опять", TAGS).name == "Зигор"
    assert find_tag("спроси у Егора!", TAGS).name == "Егор"
    assert find_tag("ЕГОРУ привет", TAGS).name == "Егор"


def test_find_tag_ignores_unrelated_words():
    assert find_tag("пригорело", TAGS) is None
    assert find_tag("егоркинский район", TAGS) is None
    assert find_tag("", TAGS) is None
