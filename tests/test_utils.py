from bot.utils import Cooldown, chunks, is_addressed, mention, strip_mention, who_question
from tests.helpers import FakeClock


def test_mention_escapes_name() -> None:
    assert mention(42, "<b>x</b>") == '<a href="tg://user?id=42">&lt;b&gt;x&lt;/b&gt;</a>'


def test_strip_mention() -> None:
    assert strip_mention("@SglypaBot  ну  ты  даёшь", "sglypabot") == "ну ты даёшь"


def test_is_addressed() -> None:
    def called(text: str, reply_to: int | None = None) -> bool:
        return is_addressed(
            text, reply_to_user_id=reply_to, bot_id=1, bot_username="SglypaBot", triggers=("бот",)
        )

    assert called("эй @sglypabot")
    assert called("Сглыпа, скажи")
    assert called("ну ты бот")
    assert called("что", reply_to=1)
    assert not called("обычный текст", reply_to=2)


def test_cooldown() -> None:
    clock = FakeClock()
    cooldown = Cooldown(60, clock)
    assert cooldown.ready("k")
    assert not cooldown.ready("k")
    assert cooldown.ready("other")
    clock.t += 61
    assert cooldown.ready("k")
    free = Cooldown(0)
    assert free.ready("x") and free.ready("x")


def test_chunks() -> None:
    assert list(chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_who_question() -> None:
    assert who_question("кто насрал") == "насрал"
    assert who_question("Сглыпа, кто насрал?") == "насрал"
    assert who_question("@sglyper_bot кто Насрал в чате") == "насрал в чате"
    assert who_question("кто насрал сглыпа") == "насрал"
    assert who_question("никто не пришёл") is None
    assert who_question("сглыпа привет") is None
