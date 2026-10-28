"""Small helpers shared by handlers: mentions, addressing the bot, cooldowns."""

import html
import re
import time
from collections.abc import Callable, Hashable, Iterable, Iterator

GROUP_TYPES = frozenset({"group", "supergroup"})
# сглыпа, сглыпу, сглыпон, сглыпарик, зглыпа, слыпа, глыпское, сгныпена, снлыпа...
NAME_RE = re.compile(r"(?:сг|зг|сн|с|г)[лн]ып|слып|глып")
_WHO = re.compile(r"(?:^|[\s,.!:])кто\s+([^?!.\n]{1,60})", re.IGNORECASE)


def mention(user_id: int, name: str | None) -> str:
    """Clickable HTML mention that pings the user even without a @username."""
    return f'<a href="tg://user?id={int(user_id)}">{html.escape(name or "безымянный")}</a>'


def is_addressed(
    text: str,
    *,
    reply_to_user_id: int | None,
    bot_id: int,
    bot_username: str | None,
    triggers: Iterable[str],
) -> bool:
    """True if the message replies to the bot, @mentions it or calls it by any form of its name."""
    if reply_to_user_id == bot_id:
        return True
    lowered = text.lower()
    if bot_username and f"@{bot_username.lower()}" in lowered:
        return True
    return bool(NAME_RE.search(lowered)) or any(t in lowered for t in triggers)


def who_question(text: str) -> str | None:
    """'сглыпа, кто насрал?' -> 'насрал'. The bot's own names are dropped from the answer."""
    m = _WHO.search(text)
    if not m:
        return None
    words = [w for w in m.group(1).split() if not NAME_RE.search(w.lower()) and not w.startswith("@")]
    what = " ".join(words).strip(" ,")
    return what[:1].lower() + what[1:] if what else None


def strip_mention(text: str, bot_username: str | None) -> str:
    if bot_username:
        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Cooldown:
    """Lets an action through for a key at most once per seconds."""

    MAX_KEYS = 10_000

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.seconds = seconds
        self._clock = clock
        self._last: dict[Hashable, float] = {}

    def ready(self, key: Hashable) -> bool:
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self.seconds:
            return False
        self._last[key] = now
        if len(self._last) > self.MAX_KEYS:
            self._last = {k: t for k, t in self._last.items() if now - t < self.seconds}
        return True
