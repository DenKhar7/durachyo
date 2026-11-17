"""Daily stuff: loser of the day, horoscopes, and the «кто это сказал» quiz."""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date

SIGNS = (
    "Пельмень", "Скуф", "Абобус", "Кринж", "Жаба", "Сигма", "Альтушка", "Нпс",
    "Шаурма", "Дед инсайд", "Бомж", "Таракан",
)  # fmt: skip
LOSER_DRAMA = (
    "Внимание, начинаю поиск лоха дня...",
    "Сканирую переписку... ищу самые тупые сообщения...",
    "Сверяю с базой данных ФСБ...",
    "Так-так-так, кажется, нашёл...",
)
LOSER_LINES = (
    "🤡 Лох дня: {name}. Поздравляем, ты лох",
    "🤡 Сегодня лох - {name}. Ничего личного, просто ты лох",
    "🤡 {name}, это ты. Ты лох дня",
)
FORECASTS = (
    "Сегодня звёзды говорят тебе: «{phrase}»",
    "День начнётся с «{phrase}», а закончится ещё хуже",
    "Вселенная шепчет: «{phrase}». Прислушайся",
)


def day_seed(*parts: object) -> int:
    # not hash(): python salts it differently on every start, picks would change after a restart
    digest = hashlib.sha256(":".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def day_rng(*parts: object) -> random.Random:
    return random.Random(day_seed(*parts))


def sign_of(user_id: int) -> str:
    """The same «знак зодиака» forever, it's your sign after all."""
    return SIGNS[day_seed("sign", user_id) % len(SIGNS)]


@dataclass(slots=True)
class Quiz:
    author_id: int
    author_name: str
    phrase: str
    guessed: set[int] = field(default_factory=set)  # everyone who already tried


def today_key(day: date) -> str:
    return day.isoformat()
