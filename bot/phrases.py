"""Old phrases of the chat that the bot says as its own."""

from collections.abc import Collection, Iterable

from bot.db import Database

MIN_SKIP = 20
MAX_SKIP = 300
RANDOM_TRIES = 3


async def phrase_skip(db: Database, chat_id: int) -> int:
    """How many newest messages are too fresh to repeat: a phrase only lands once people forgot it."""
    total, _ = await db.stats(chat_id)
    return min(MAX_SKIP, max(MIN_SKIP, total // 4))


async def pick_phrase(
    db: Database,
    chat_id: int,
    words: Iterable[str] = (),
    avoid: Collection[str] = frozenset(),
    *,
    max_words: int = 12,
) -> str | None:
    """An old phrase containing one of words (tried in order), else a random old phrase."""
    skip = await phrase_skip(db, chat_id)
    for word in [*words, *[None] * RANDOM_TRIES]:
        phrase = await db.old_phrase(chat_id, skip, word=word, max_words=max_words)
        if phrase and phrase.strip().lower() not in avoid:
            return phrase
    return None
