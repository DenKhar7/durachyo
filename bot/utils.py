import html
import re
import time
from collections.abc import Hashable, Iterable

GROUP_TYPES = frozenset({"group", "supergroup"})
# сглыпа, сглыпу, сглыпон, сглыпарик, зглыпа, слыпа, глыпское, сгныпена, снлыпа...
NAME_RE = re.compile(r"(?:сг|зг|сн|с|г)[лн]ып|слып|глып")


def mention(user_id: int, name: str | None) -> str:
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


def strip_mention(text: str, bot_username: str | None) -> str:
    if bot_username:
        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def chunks[T](items: list[T], size: int) -> Iterable[list[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Cooldown:
    def __init__(self) -> None:
        self._last: dict[Hashable, float] = {}

    def ready(self, key: Hashable, seconds: float) -> bool:
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and now - last < seconds:
            return False
        self._last[key] = now
        if len(self._last) > 10_000:
            self._last = {k: v for k, v in self._last.items() if now - v < seconds}
        return True
