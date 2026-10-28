from bot.db import Database


async def test_messages_are_trimmed(db: Database) -> None:
    for i in range(5):
        await db.add_message(-1, 10, f"msg {i}", keep=3)
    await db.add_message(-2, 10, "other chat", keep=3)
    assert await db.texts(-1) == ["msg 2", "msg 3", "msg 4"]
    assert await db.texts(-2) == ["other chat"]


async def test_users_and_reply_chance(db: Database) -> None:
    await db.upsert_user(-1, 10, "Вася", "Vasya")
    await db.upsert_user(-1, 10, "Василий", "Vasya")
    await db.upsert_user(-1, 11, "Петя", None)
    found = await db.find_user_by_username(-1, "vasya")
    assert found is not None and found.full_name == "Василий"
    assert len(await db.users(-1)) == 2
    assert await db.reply_chance(-1, 5) == 5
    await db.set_reply_chance(-1, 30)
    assert await db.reply_chance(-1, 5) == 30


async def test_tags(db: Database) -> None:
    await db.set_tag(-1, "зигор", "Зигор", "педофайл")
    await db.set_tag(-1, "зигор", "Зигор", "нуб")
    await db.set_tag(-2, "егор", "Егор", "x")
    assert [(t.name, t.label) for t in await db.tags(-1)] == [("Зигор", "нуб")]
    assert await db.delete_tag(-1, "зигор")
    assert not await db.delete_tag(-1, "зигор")


async def test_old_phrase_skips_recent_and_matches_word(db: Database) -> None:
    for i in range(10):
        await db.add_message(-1, 10, f"фраза номер {i}", keep=100)
    await db.add_message(-1, 10, "Привет ПИВО холодное", keep=100)
    await db.add_message(-1, 10, "одно", keep=100)
    for i in range(5):
        await db.add_message(-1, 10, f"свежак {i} тут", keep=100)
    old = {await db.old_phrase(-1, 5) for _ in range(40)}
    assert old and all(p and not p.startswith("свежак") for p in old)
    assert "одно" not in old
    assert await db.old_phrase(-1, 5, word="пиво") == "Привет ПИВО холодное"
    assert await db.old_phrase(-1, 50) is None


async def test_old_phrase_treats_like_wildcards_literally(db: Database) -> None:
    await db.add_message(-1, 10, "код a1x0 тут", keep=100)
    await db.add_message(-1, 10, "код 1_0 тут", keep=100)
    for _ in range(10):
        assert await db.old_phrase(-1, 0, word="1_0") == "код 1_0 тут"


async def test_short_phrases_counts_repeats(db: Database) -> None:
    for text in ["Го", "го", "го", "база", "База", "одна фраза тут длинная", "пон"]:
        await db.add_message(-1, 10, text, keep=100)
    assert await db.short_phrases(-1) == [("го", 3), ("база", 2)]


async def test_media_and_hits(db: Database) -> None:
    for i in range(5):
        await db.add_media(-1, "sticker", f"u{i}", f"f{i}", emoji="😂", keep=3)
    await db.add_media(-1, "sticker", "u4", "f4-new", keep=3)
    stickers = {await db.random_media(-1, "sticker") for _ in range(40)}
    assert stickers <= {"f2", "f3", "f4-new"} and "f4-new" in stickers
    assert await db.random_media(-1, "photo") is None
    for text in ("normalno", "normalno", "го"):
        await db.add_hit(-1, text)
    assert await db.hits(-1) == [("normalno", 2), ("го", 1)]


async def test_forget_user(db: Database) -> None:
    await db.upsert_user(-1, 10, "Вася", None)
    await db.add_message(-1, 10, "a", keep=100)
    await db.add_message(-1, 11, "b", keep=100)
    assert await db.forget_user(-1, 10) == 1
    assert await db.texts(-1) == ["b"]
    assert await db.get_user(-1, 10) is None
    assert await db.stats(-1) == (1, 0)
