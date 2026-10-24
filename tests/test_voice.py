import random

from bot.nicknames import find_nick, nick_line
from bot.utils import is_addressed
from bot.voice import casual, is_laugh


def test_casual_drops_period_and_keeps_verbatim_case():
    rng = random.Random(0)
    assert casual("Ну и дела.", rng, verbatim=True) == "Ну и дела"
    assert casual("ну и дела...", rng, verbatim=True) == "ну и дела..."
    outs = {casual("Ну и дела.", random.Random(i)) for i in range(50)}
    assert all(not o.endswith(".") for o in outs)
    assert any(o.startswith("ну") for o in outs)


def test_is_laugh():
    assert is_laugh("АХАХАХАХ") and is_laugh("ору") and is_laugh("хД") and is_laugh(None, "😂")
    assert not is_laugh("лоли жаба") and not is_laugh("хорошо") and not is_laugh(None, "👍")


def test_name_variants_call_the_bot():
    kw = dict(reply_to_user_id=None, bot_id=1, bot_username="x_bot", triggers=())
    for text in ["сглыпу позовите", "Сглыпон", "зглыпа", "сглыпарик", "СГНЫПЕНА ебана", "снлыпа", "глыпское", "агрослыпик"]:
        assert is_addressed(text, **kw), text
    for text in ["глыба", "слышь", "пошли гулять"]:
        assert not is_addressed(text, **kw), text


def test_nicknames_match_forms_not_lookalikes():
    assert find_nick("где Маша").name == "Маша"
    assert find_nick("машке передай").name == "Маша"
    assert find_nick("скажи Лесону").name == "Лесон"
    assert find_nick("дениска опять").name == "Денис"
    assert find_nick("ЕГОРУ привет").name == "Егор"
    assert find_nick("зигагор тут").name == "Зигагор"
    assert find_nick("Зигагору привет").name == "Зигагор"
    assert find_nick("зигогора нет").name == "Зигогор"
    assert find_nick("Зигор!").name == "Зигор"
    assert find_nick("машина сломалась") is None
    assert find_nick("пригорело") is None
    assert find_nick("денег нет") is None


def test_nick_lines():
    rng = random.Random(0)
    assert nick_line(find_nick("Маша"), rng) in {"Маша - свинья", "Маша - псина"}
    assert nick_line(find_nick("егор"), rng) in {"Егор = пдфайл", "Егор = лоликонщик", "Егор = лоли"}
    assert nick_line(find_nick("зигагор"), rng) in {"Зигагор = пдфайл", "Зигагор = лоликонщик", "Зигагор = лоли"}
    assert nick_line(find_nick("Зигору"), rng) in {"Зигор = пдфайл", "Зигор = лоликонщик", "Зигор = лоли"}
