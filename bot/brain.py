import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ChatState:
    since_bot: int = 0
    last_activity: float = 0.0
    last_bot_post: float = 0.0
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=20))
    recent_bot: deque[str] = field(default_factory=lambda: deque(maxlen=40))
    last_bot_plain: str | None = None
    last_bot_id: int | None = None
    scored: bool = True


@dataclass(frozen=True, slots=True)
class Context:
    addressed: bool = False
    tagged: bool = False
    reply_to_other: bool = False
    words: int = 0
    question: bool = False
    shouting: bool = False
    media: str | None = None


def analyze(
    text: str,
    *,
    addressed: bool = False,
    tagged: bool = False,
    reply_to_other: bool = False,
    media: str | None = None,
) -> Context:
    letters = [ch for ch in text if ch.isalpha()]
    return Context(
        addressed=addressed,
        tagged=tagged,
        reply_to_other=reply_to_other,
        media=media,
        words=len(text.split()),
        question="?" in text,
        shouting=len(letters) >= 5 and all(ch.isupper() for ch in letters),
    )


class Brain:
    """Decides on its own when to speak: reacts to what's said and how lively the chat is,
    backs off right after talking, gets chattier when it has been quiet for a while."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._chats: dict[int, ChatState] = {}

    def state(self, chat_id: int) -> ChatState:
        return self._chats.setdefault(chat_id, ChatState())

    def observe(self, chat_id: int, text: str | None = None) -> ChatState:
        s = self.state(chat_id)
        s.since_bot += 1
        s.last_activity = self._clock()
        if text:
            s.recent.append(text)
        return s

    def spoke(self, chat_id: int, plain: str | None = None, message_id: int | None = None) -> None:
        s = self.state(chat_id)
        s.since_bot = 0
        s.last_bot_post = self._clock()
        s.last_bot_plain = plain
        s.last_bot_id = message_id
        s.scored = plain is None
        if plain:
            s.recent_bot.append(plain.strip().lower())

    def reply_probability(self, chat_id: int, ctx: Context, base: int, called_chance: int = 100) -> float:
        if ctx.addressed:
            return float(called_chance)
        if base <= 0:
            return 0.0
        p = float(base)
        if ctx.tagged:
            p += 40
        if ctx.question:
            p += 15
        if ctx.shouting:
            p += 15
        if ctx.media is None:
            if ctx.words >= 8:
                p += 10
            elif ctx.words <= 1:
                p -= 15
        since = self.state(chat_id).since_bot
        if since <= 1:
            p *= 0.25
        elif since <= 3:
            p *= 0.6
        elif since >= 10:
            p += 20
        return max(0.0, min(100.0, p))

    def should_reply(
        self, chat_id: int, ctx: Context, base: int, called_chance: int = 100, rng: random.Random | None = None
    ) -> bool:
        return (rng or random).random() * 100 < self.reply_probability(chat_id, ctx, base, called_chance)

    def needs_revive(self, chat_id: int, idle_seconds: float) -> bool:
        s = self._chats.get(chat_id)
        if idle_seconds <= 0 or s is None or not s.last_activity:
            return False
        return self._clock() - s.last_activity >= idle_seconds and s.last_bot_post < s.last_activity
