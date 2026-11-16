import html
import re
import time
from collections import deque
from collections.abc import Callable, Hashable, Iterable, Iterator

GROUP_TYPES = frozenset({"group", "supergroup"})
# сглыпа, сглыпу, сглыпон, сглыпарик, зглыпа, слыпа, глыпское, сгныпена, снлыпа...
NAME_RE = re.compile(r"(?:сг|зг|сн|с|г)[лн]ып|слып|глып")
_WHO = re.compile(r"(?:^|[\s,.!:])кто\s+([^?!.\n]{1,60})", re.IGNORECASE)


def mention(user_id: int, name: str | None) -> str:
    # works for people without a @username too
    return f'<a href="tg://user?id={int(user_id)}">{html.escape(name or "безымянный")}</a>'


def is_addressed(
    text: str,
    *,
    reply_to_user_id: int | None,
    bot_id: int,
    bot_username: str | None,
    triggers: Iterable[str],
) -> bool:
    if reply_to_user_id == bot_id:
        return True
    lowered = text.lower()
    if bot_username and f"@{bot_username.lower()}" in lowered:
        return True
    return bool(NAME_RE.search(lowered)) or any(t in lowered for t in triggers)


def who_question(text: str) -> str | None:
    """'сглыпа, кто насрал?' -> 'насрал'"""
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


class RateLimit:
    """At most limit actions per key in any window of seconds."""

    def __init__(self, limit: int, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.seconds = seconds
        self._clock = clock
        self._hits: dict[Hashable, deque[float]] = {}

    def ready(self, key: Hashable) -> bool:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
