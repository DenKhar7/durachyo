from datetime import date

from bot.toad import LEGENDARY, toad_of_the_day, toad_seed

DAY = date(2026, 10, 28)


def test_same_person_same_day_same_toad() -> None:
    assert toad_of_the_day(-1, 10, DAY) == toad_of_the_day(-1, 10, DAY)
    assert toad_seed(-1, 10, DAY) == toad_seed(-1, 10, DAY)
    assert toad_seed(-1, 10, DAY) != toad_seed(-1, 10, date(2026, 10, 29))
    assert len({toad_of_the_day(-1, user, DAY).name for user in range(30)}) > 20


def test_legendary_toads_are_strong() -> None:
    toads = [toad_of_the_day(-1, user, DAY) for user in range(2000)]
    legendary = [t for t in toads if t.rarity is LEGENDARY]
    assert 20 < len(legendary) < 120
    assert all(t.power >= 90 for t in legendary)
