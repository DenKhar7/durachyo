"""Жаба дня: everyone gets a toad name, rarity and power, the same until midnight.

The picture comes from our pinterest board (pinterest.py).
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import date

ADJECTIVES = (
    "Болотная", "Бархатная", "Токсичная", "Королевская", "Сонная", "Пупырчатая", "Космическая",
    "Депрессивная", "Гигачадовая", "Квантовая", "Анимешная", "Пьяная", "Бородавчатая", "Душная",
    "Элитная", "Подвальная", "Контуженная", "Олимпийская", "Шизанутая", "Ламповая",
)  # fmt: skip
NOUNS = (
    "пельмень", "философ", "бомж", "император", "гопник", "сигма", "скуф", "альтушка",
    "программист", "дед инсайд", "барон", "шаурма", "ниндзя", "абобус", "тиктокер", "сантехник",
    "депутат", "киберкотлета", "бабка у подъезда", "стример",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Rarity:
    name: str
    weight: int


RARITIES = (
    Rarity("обычная", 60),
    Rarity("редкая", 25),
    Rarity("эпическая", 12),
    Rarity("легендарная 👑", 3),
)
LEGENDARY = RARITIES[-1]


@dataclass(frozen=True, slots=True)
class Toad:
    name: str
    rarity: Rarity
    power: int


def toad_seed(chat_id: int, user_id: int, day: date) -> int:
    # not hash(): python salts it differently on every start and the toad would change on restart
    digest = hashlib.sha256(f"{chat_id}:{user_id}:{day.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def toad_of_the_day(chat_id: int, user_id: int, day: date) -> Toad:
    rng = random.Random(toad_seed(chat_id, user_id, day))
    rarity = rng.choices(RARITIES, weights=[r.weight for r in RARITIES])[0]
    power = rng.randint(90, 100) if rarity is LEGENDARY else rng.randint(1, 89)
    return Toad(f"{rng.choice(ADJECTIVES)} жаба-{rng.choice(NOUNS)}", rarity, power)
