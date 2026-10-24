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
