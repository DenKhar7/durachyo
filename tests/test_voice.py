import random

from bot.utils import is_addressed
from bot.voice import casual, is_laugh


def test_casual_drops_period_and_keeps_verbatim_case() -> None:
    rng = random.Random(0)
    assert casual("Ну и дела.", rng, verbatim=True) == "Ну и дела"
    assert casual("ну и дела...", rng, verbatim=True) == "ну и дела..."
    outs = {casual("Ну и дела.", random.Random(i)) for i in range(50)}
    assert all(not o.endswith(".") for o in outs)
    assert any(o.startswith("ну") for o in outs)


def test_is_laugh() -> None:
    assert is_laugh("АХАХАХАХ") and is_laugh("ору") and is_laugh("хД") and is_laugh(None, "😂")
    assert not is_laugh("лоли жаба") and not is_laugh("хорошо") and not is_laugh(None, "👍")


def test_name_variants_call_the_bot() -> None:
    def called(text: str) -> bool:
        return is_addressed(text, reply_to_user_id=None, bot_id=1, bot_username="x_bot", triggers=())

    for text in ["сглыпу позовите", "Сглыпон", "зглыпа", "сглыпарик", "СГНЫПЕНА ебана", "снлыпа", "глыпское"]:
        assert called(text), text
    assert called("агрослыпик")
    for text in ["глыба", "слышь", "пошли гулять"]:
        assert not called(text), text
