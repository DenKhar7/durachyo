import random
from datetime import date
from unittest.mock import AsyncMock

import pytest

from bot import toad
from bot.db import Database
from bot.toad import LEGENDARY, MemeLink, ToadPool, parse_memes, toad_of_the_day

DAY = date(2026, 10, 28)  # a Wednesday
THURSDAY = date(2026, 10, 29)


def test_same_person_same_day_same_toad() -> None:
    assert toad_of_the_day(-1, 10, DAY) == toad_of_the_day(-1, 10, DAY)
    assert len({toad_of_the_day(-1, user, DAY).name for user in range(30)}) > 20


def test_legendary_toads_are_strong() -> None:
    toads = [toad_of_the_day(-1, user, DAY) for user in range(2000)]
    legendary = [t for t in toads if t.rarity is LEGENDARY]
    assert 20 < len(legendary) < 120
    assert all(t.power >= 90 for t in legendary)


def test_parse_memes_keeps_safe_pictures_and_gifs() -> None:
    payload = {
        "memes": [
            {"url": "https://i.redd.it/a.jpg", "nsfw": False, "spoiler": False},
            {
                "url": "https://i.redd.it/w.jpg",
                "nsfw": False,
                "spoiler": False,
                "title": "It is Wednesday my dudes",
            },
            {"url": "https://i.redd.it/b.gif", "nsfw": False, "spoiler": False},
            {"url": "https://i.redd.it/c.jpg", "nsfw": True, "spoiler": False},
            {"url": "https://v.redd.it/video", "nsfw": False, "spoiler": False},
            {"url": "http://i.redd.it/d.png", "nsfw": False, "spoiler": False},
        ]
    }
    assert parse_memes(payload, "frogmemes") == [
        MemeLink("photo", "https://i.redd.it/a.jpg", "frogmemes"),
        MemeLink("photo", "https://i.redd.it/w.jpg", "wednesday"),
        MemeLink("animation", "https://i.redd.it/b.gif", "frogmemes"),
    ]
    assert parse_memes({}, "x") == []


async def stock(db: Database) -> None:
    links = [("photo", "frogmemes", f"https://x/{i}.jpg") for i in range(5)]
    links.append(("photo", "wednesday", "https://x/wed.jpg"))
    assert await db.add_toad_memes(links) == 6
    assert await db.add_toad_memes(links) == 0


async def test_pick_is_stable_per_day_and_unique_in_chat(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    await stock(db)
    monkeypatch.setattr(toad, "POOL_TARGET", 1)
    pool, rng = ToadPool(), random.Random(0)
    pool._last_refill = 1e18  # fresh: no network
    first = await pool.pick(db, -1, 10, THURSDAY, rng)
    assert first is not None and first.source == "frogmemes"
    assert await pool.pick(db, -1, 10, THURSDAY, rng) == first
    others = [await pool.pick(db, -1, user, THURSDAY, rng) for user in range(11, 15)]
    assert len({m.id for m in others if m} | {first.id}) == 5
    assert await pool.pick(db, -1, 99, THURSDAY, rng) is None  # only the wednesday one is left


async def test_wednesday_meme_comes_first_on_wednesday(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    await stock(db)
    monkeypatch.setattr(toad, "POOL_TARGET", 1)
    pool = ToadPool()
    pool._last_refill = 1e18
    meme = await pool.pick(db, -1, 10, DAY, random.Random(0))
    assert meme is not None and meme.source == "wednesday"


async def test_chat_collection_and_dead_memes(db: Database) -> None:
    assert await db.add_chat_toad(-1, "sticker", "u1", "F1")
    assert not await db.add_chat_toad(-1, "sticker", "u1", "F1")
    assert await db.toad_meme_count(-1) == 1 and await db.toad_meme_count() == 0
    meme = await db.pick_toad_meme(-1, DAY, own=True, wednesday=False)
    assert meme is not None and meme.file_id == "F1" and meme.kind == "sticker"
    assert await db.pick_toad_meme(-2, DAY, own=True, wednesday=False) is None
    await db.give_toad(-1, 10, DAY, meme.id)
    await db.drop_toad_meme(meme.id)
    assert await db.toad_of_day(-1, 10, DAY) is None


async def test_refill_fetches_every_subreddit(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(session: object, subreddit: str) -> list[MemeLink]:
        return [MemeLink("photo", f"https://x/{subreddit}.jpg", subreddit)]

    monkeypatch.setattr(toad, "fetch_memes", AsyncMock(side_effect=fake_fetch))
    assert await ToadPool().refill(db, force=True) == len(toad.SUBREDDITS)


async def test_prune_keeps_pool_small_and_todays_toads(db: Database) -> None:
    await db.add_toad_memes([("photo", "frogmemes", f"https://x/{i}.jpg") for i in range(10)])
    held = await db.pick_toad_meme(-1, DAY, own=False, wednesday=False)
    assert held is not None
    await db.give_toad(-1, 10, DAY, held.id)
    await db.give_toad(-1, 11, date(2026, 10, 1), held.id)
    await db.prune_toads(DAY, keep_shared=3, sources=("frogmemes",))
    assert await db.toad_meme_count() <= 4
    assert await db.toad_of_day(-1, 10, DAY) == held
    assert await db.toad_of_day(-1, 11, date(2026, 10, 1)) is None


async def test_prune_drops_retired_sources_even_if_held(db: Database) -> None:
    await db.add_toad_memes([("photo", "itswednesdaymydudes", "https://x/guy.jpg")])
    await db.add_toad_memes([("photo", "frogmemes", "https://x/frog.jpg")])
    await db.add_chat_toad(-1, "sticker", "u", "F")
    guy = await db.pick_toad_meme(-1, DAY, own=False, wednesday=False)
    while guy is not None and guy.source != "itswednesdaymydudes":
        guy = await db.pick_toad_meme(-1, DAY, own=False, wednesday=False)
    assert guy is not None
    await db.give_toad(-1, 10, DAY, guy.id)
    await db.prune_toads(DAY, keep_shared=100, sources=("frogmemes", "wednesday"))
    assert await db.toad_of_day(-1, 10, DAY) is None
    assert await db.toad_meme_count() == 1
    assert await db.toad_meme_count(-1) == 1
