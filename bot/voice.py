import random
import re

BASE_SHORT = (
    "ахахах",
    "ахахахах",
    "ахахахаха",
    "бля",
    "да",
    "го",
    "пон",
    "жиза",
    "база",
    "ну такое",
    "чё",
    "ага",
    "сука",
    "пиздец",
    "😂",
    "🗿",
    "🙂",
    "😐",
    "💀",
    "😈",
)
LAUGHS = ("ахахах", "ахахахах", "АХАХАХАХ", "😂", "хД", "бля ахаха")
EMOJIS = ("😂", "🗿", "💀", "🙂", "😐", "😈", "🤡", "🐸")
REACTIONS = ("🗿", "💯", "🤡", "😁", "🤣", "🐳", "🔥", "👀", "🤔", "🙈", "🤓", "😐", "🫡", "✍", "💩")
LAUGH_REACTIONS = ("🤣", "😁", "💯", "🗿")
LAUGH_STICKERS = frozenset({"😂", "🤣", "😹", "😆"})
_LAUGH = re.compile(r"(ах[ах]{2,}|хах|пхп|\bхд\b|\bxd\b|\bору\b|\bржу|\bлол\b|😂|🤣)", re.IGNORECASE)


def is_laugh(text: str | None, sticker_emoji: str | None = None) -> bool:
    return bool(text and _LAUGH.search(text)) or sticker_emoji in LAUGH_STICKERS


def casual(text: str, rng: random.Random, *, verbatim: bool = False) -> str:
    """Chat voice: no trailing period, sometimes lowercase, rare хД or emoji.

    verbatim=True keeps the phrase exactly as people wrote it, only the period goes.
    """
    t = " ".join(text.split())
    if t.endswith(".") and not t.endswith(".."):
        t = t[:-1]
    if verbatim or not t:
        return t
    if t[:1].isupper() and not t[:2].isupper() and rng.random() < 0.3:
        t = t[0].lower() + t[1:]
    roll = rng.random()
    if roll < 0.04:
        t += " хД"
    elif roll < 0.08:
        t += " " + rng.choice(EMOJIS)
    return t
