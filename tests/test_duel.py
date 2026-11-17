import random

from bot.db import Database, HeadToHead
from bot.duel import Fight, fight, fight_line
from bot.utils import RateLimit
from tests.helpers import FakeClock


def test_fight_outcomes() -> None:
    assert Fight(15, 3).a_won is True
    assert Fight(3, 15).a_won is False
    assert Fight(7, 7).a_won is None
    rolls = [fight(random.Random(i)) for i in range(300)]
    assert all(1 <= f.roll_a <= 20 and 1 <= f.roll_b <= 20 for f in rolls)


def test_fight_lines() -> None:
    rng = random.Random(0)
    assert "КРИТ" in fight_line(Fight(20, 5), "A", "B", rng)
    assert "КРИТ" in fight_line(Fight(5, 20), "A", "B", rng)
    assert "сам себя" in fight_line(Fight(10, 1), "A", "B", rng) or "промазал" in fight_line(
        Fight(10, 1), "A", "B", rng
    )
    draw = fight_line(Fight(8, 8), "A", "B", rng)
    assert "A" in draw and "B" in draw
    for _ in range(30):
        line = fight_line(Fight(12, 4), "A", "B", rng)
        assert "A" in line and "B" in line and "{" not in line


def test_rate_limit_window() -> None:
    clock = FakeClock()
    limit = RateLimit(5, 60, clock)
    assert all(limit.ready("chat") for _ in range(5))
    assert not limit.ready("chat")
    assert limit.ready("other chat")
    clock.t += 30
    assert not limit.ready("chat")
    clock.t += 31
    assert limit.ready("chat")


async def test_duel_stats_and_streaks(db: Database) -> None:
    await db.upsert_user(-1, 10, "Вася", None)
    for _ in range(3):
        await db.record_duel(-1, 10, a=10, b=11)
    vasya = await db.duelist(-1, 10)
    assert (vasya.name, vasya.wins, vasya.losses, vasya.streak, vasya.best_streak) == ("Вася", 3, 0, 3, 3)
    await db.record_duel(-1, 11, a=10, b=11)
    await db.record_duel(-1, None, a=10, b=11)
    vasya, petya = await db.duelist(-1, 10), await db.duelist(-1, 11)
    assert (vasya.wins, vasya.losses, vasya.streak, vasya.best_streak) == (3, 1, 0, 3)
    assert (petya.wins, petya.losses, petya.streak, petya.name) == (1, 3, 0, None)
    assert [d.user_id for d in await db.duel_top(-1)] == [10, 11]
    assert (await db.duelist(-1, 99)).wins == 0


async def test_head_to_head_from_both_sides(db: Database) -> None:
    await db.record_duel(-1, 20, a=20, b=5)
    await db.record_duel(-1, 20, a=5, b=20)
    await db.record_duel(-1, 5, a=5, b=20)
    await db.record_duel(-1, None, a=20, b=5)
    assert await db.head_to_head(-1, 20, 5) == HeadToHead(2, 1, 1)
    assert await db.head_to_head(-1, 5, 20) == HeadToHead(1, 2, 1)
    assert await db.head_to_head(-1, 5, 99) == HeadToHead()
    assert await db.head_to_head(-2, 5, 20) == HeadToHead()
    (rival,) = await db.rivals(-1, 5)
    assert rival.user_id == 20 and rival.score == HeadToHead(1, 2, 1)
