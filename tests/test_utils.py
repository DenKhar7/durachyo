from bot.utils import Cooldown, chunks, is_addressed, mention, strip_mention, who_question


def test_mention_escapes_name():
    assert mention(42, "<b>x</b>") == '<a href="tg://user?id=42">&lt;b&gt;x&lt;/b&gt;</a>'


def test_strip_mention():
    assert strip_mention("@SglypaBot  ну  ты  даёшь", "sglypabot") == "ну ты даёшь"


def test_is_addressed():
    kw = dict(bot_id=1, bot_username="SglypaBot", triggers=("сглыпа",))
    assert is_addressed("эй @sglypabot", reply_to_user_id=None, **kw)
    assert is_addressed("Сглыпа, скажи", reply_to_user_id=None, **kw)
    assert is_addressed("что", reply_to_user_id=1, **kw)
    assert not is_addressed("обычный текст", reply_to_user_id=2, **kw)


def test_cooldown():
    cd = Cooldown()
    assert cd.ready("k", 60)
    assert not cd.ready("k", 60)
    assert cd.ready("other", 60)
    assert cd.ready("k", 0)


def test_chunks():
    assert list(chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_who_question():
    assert who_question("кто насрал") == "насрал"
    assert who_question("Сглыпа, кто насрал?") == "насрал"
    assert who_question("@sglyper_bot кто Насрал в чате") == "насрал в чате"
    assert who_question("кто насрал сглыпа") == "насрал"
    assert who_question("никто не пришёл") is None
    assert who_question("сглыпа привет") is None
