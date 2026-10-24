import random
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ChatState:
    since_bot: int = 0
    last_activity: float = 0.0
    last_bot_post: float = 0.0


@dataclass(frozen=True, slots=True)
class Context:
    addressed: bool = False
    tagged: bool = False
    reply_to_other: bool = False
    words: int = 0
    question: bool = False
    shouting: bool = False


def analyze(text: str, *, addressed: bool = False, tagged: bool = False, reply_to_other: bool = False) -> Context:
    letters = [ch for ch in text if ch.isalpha()]
    return Context(
        addressed=addressed,
        tagged=tagged,
        reply_to_other=reply_to_other,
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

    def observe(self, chat_id: int) -> None:
        s = self.state(chat_id)
        s.since_bot += 1
        s.last_activity = self._clock()

    def spoke(self, chat_id: int) -> None:
        s = self.state(chat_id)
        s.since_bot = 0
        s.last_bot_post = self._clock()

    def reply_probability(self, chat_id: int, ctx: Context, base: int) -> float:
        if ctx.addressed:
            return 100.0
        if base <= 0:
            return 0.0
        p = float(base)
        if ctx.tagged:
            p += 40
        if ctx.question:
            p += 15
        if ctx.shouting:
            p += 15
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

    def should_reply(self, chat_id: int, ctx: Context, base: int, rng: random.Random | None = None) -> bool:
        return (rng or random).random() * 100 < self.reply_probability(chat_id, ctx, base)

    def needs_revive(self, chat_id: int, idle_seconds: float) -> bool:
        s = self._chats.get(chat_id)
        if idle_seconds <= 0 or s is None or not s.last_activity:
            return False
        return self._clock() - s.last_activity >= idle_seconds and s.last_bot_post < s.last_activity
