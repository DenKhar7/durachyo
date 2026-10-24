import asyncio

from bot.db import Database


def run(coro):
    return asyncio.run(coro)


def test_messages_are_trimmed(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        for i in range(5):
            await db.add_message(-1, 10, f"msg {i}", keep=3)
        await db.add_message(-2, 10, "other chat", keep=3)
        texts = await db.texts(-1)
        await db.close()
        return texts

    assert run(scenario()) == ["msg 2", "msg 3", "msg 4"]


def test_users_and_settings(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        await db.upsert_user(-1, 10, "Вася", "Vasya")
        await db.upsert_user(-1, 10, "Василий", "Vasya")
        await db.upsert_user(-1, 11, "Петя", None)
        found = await db.find_user_by_username(-1, "vasya")
        users = await db.users(-1)
        default = await db.reply_chance(-1, 5)
        await db.set_reply_chance(-1, 30)
        changed = await db.reply_chance(-1, 5)
        await db.close()
        return found, users, default, changed

    found, users, default, changed = run(scenario())
    assert found.full_name == "Василий"
    assert len(users) == 2
    assert (default, changed) == (5, 30)


def test_tags(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        await db.set_tag(-1, "зигор", "Зигор", "педофайл")
        await db.set_tag(-1, "зигор", "Зигор", "нуб")
        await db.set_tag(-2, "егор", "Егор", "x")
        tags = await db.tags(-1)
        removed = await db.delete_tag(-1, "зигор")
        missing = await db.delete_tag(-1, "зигор")
        await db.close()
        return tags, removed, missing

    tags, removed, missing = run(scenario())
    assert [(t.name, t.label) for t in tags] == [("Зигор", "нуб")]
    assert (removed, missing) == (True, False)


def test_old_phrase_skips_recent_and_matches_word(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        for i in range(10):
            await db.add_message(-1, 10, f"фраза номер {i}", keep=100)
        await db.add_message(-1, 10, "Привет ПИВО холодное", keep=100)
        await db.add_message(-1, 10, "одно", keep=100)
        for i in range(5):
            await db.add_message(-1, 10, f"свежак {i} тут", keep=100)
        old = {await db.old_phrase(-1, 5) for _ in range(40)}
        beer = await db.old_phrase(-1, 5, word="пиво")
        none = await db.old_phrase(-1, 50)
        await db.close()
        return old, beer, none

    old, beer, none = run(scenario())
    assert not any(p.startswith("свежак") for p in old)
    assert "одно" not in old
    assert beer == "Привет ПИВО холодное" and none is None


def test_short_phrases_counts_repeats(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        for text in ["Го", "го", "го", "база", "База", "одна фраза тут длинная", "пон"]:
            await db.add_message(-1, 10, text, keep=100)
        pool = await db.short_phrases(-1)
        await db.close()
        return pool

    assert run(scenario()) == [("го", 3), ("база", 2)]


def test_media_and_hits(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        for i in range(5):
            await db.add_media(-1, "sticker", f"u{i}", f"f{i}", "😂", keep=3)
        await db.add_media(-1, "sticker", "u4", "f4-new", "😂", keep=3)
        stickers = {await db.random_media(-1, "sticker") for _ in range(40)}
        photo = await db.random_media(-1, "photo")
        await db.add_hit(-1, "normalno")
        await db.add_hit(-1, "normalno")
        await db.add_hit(-1, "го")
        hits = await db.hits(-1)
        await db.close()
        return stickers, photo, hits

    stickers, photo, hits = run(scenario())
    assert stickers <= {"f2", "f3", "f4-new"} and "f4-new" in stickers
    assert photo is None
    assert hits == [("normalno", 2), ("го", 1)]


def test_forget_user(tmp_path):
    async def scenario():
        db = await Database.open(tmp_path / "t.db")
        await db.upsert_user(-1, 10, "Вася", None)
        await db.add_message(-1, 10, "a", keep=100)
        await db.add_message(-1, 11, "b", keep=100)
        deleted = await db.forget_user(-1, 10)
        texts = await db.texts(-1)
        user = await db.get_user(-1, 10)
        await db.close()
        return deleted, texts, user

    assert run(scenario()) == (1, ["b"], None)
