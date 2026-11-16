from collections.abc import Collection, Iterable

from bot.db import Database

MIN_SKIP = 20
MAX_SKIP = 300
RANDOM_TRIES = 3


async def phrase_skip(db: Database, chat_id: int) -> int:
    """How many of the newest messages are off limits.

    Repeating what was said five minutes ago is just an echo. The joke works when people
    recognise the phrase but can't remember who said it, so the newest quarter of the chat
    (20 messages at least, 300 at most) is left alone.
    """
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
    """An old phrase with one of the words in it, or just a random old one."""
    skip = await phrase_skip(db, chat_id)
    for word in [*words, *[None] * RANDOM_TRIES]:
        phrase = await db.old_phrase(chat_id, skip, word=word, max_words=max_words)
        if phrase and phrase.strip().lower() not in avoid:
            return phrase
    return None
