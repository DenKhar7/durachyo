import random
import re
from collections import Counter, defaultdict

START = "\x02"
END = "\x03"
_NON_WORD = re.compile(r"[^\w]+")

State = tuple[str, ...]


def normalize(word: str) -> str:
    return _NON_WORD.sub("", word.lower())


class MarkovChain:
    """Word-level n-gram chain. order = how many previous words define the next one."""

    def __init__(self, order: int = 2) -> None:
        if order < 1:
            raise ValueError("order must be >= 1")
        self.order = order
        self._model: dict[State, Counter[str]] = defaultdict(Counter)
        self._index: dict[str, set[State]] = defaultdict(set)
        self._originals: set[str] = set()
        self._counts: Counter[str] = Counter()

    def __len__(self) -> int:
        return len(self._originals)

    def add(self, text: str) -> None:
        tokens = text.split()
        if not tokens:
            return
        self._originals.add(" ".join(tokens))
        self._counts.update(k for k in map(normalize, tokens) if k)
        seq = [START] * self.order + tokens + [END]
        for i in range(len(seq) - self.order):
            state = tuple(seq[i : i + self.order])
            self._model[state][seq[i + self.order]] += 1
            key = normalize(state[-1])
            if key:
                self._index[key].add(state)

    def known(self, word: str) -> bool:
        key = normalize(word)
        return bool(key) and key in self._index

    def frequency(self, word: str) -> int:
        return self._counts.get(normalize(word), 0)

    def vocabulary(self) -> tuple[str, ...]:
        return tuple(self._counts)

    def random_word(self, rng: random.Random | None = None) -> str | None:
        if not self._index:
            return None
        return (rng or random).choice(tuple(self._index))

    def generate(
        self,
        seed: str | None = None,
        *,
        max_words: int = 30,
        tries: int = 10,
        rng: random.Random | None = None,
    ) -> str | None:
        """Random walk. Prefers results that are not verbatim copies of a stored message."""
        rng = rng or random
        fallback: str | None = None
        for _ in range(tries):
            text = self._walk(seed, max_words, rng)
            if text is None:
                return fallback
            if text not in self._originals:
                return text
            fallback = fallback or text
        return fallback

    def _walk(self, seed: str | None, max_words: int, rng: random.Random) -> str | None:
        if seed is None:
            state: State = (START,) * self.order
            words: list[str] = []
        else:
            states = self._index.get(normalize(seed))
            if not states:
                return None
            state = rng.choice(tuple(states))
            words = [w for w in state if w != START]
        while len(words) < max_words:
            choices = self._model.get(state)
            if not choices:
                break
            nxt = rng.choices(tuple(choices), weights=tuple(choices.values()))[0]
            if nxt == END:
                break
            words.append(nxt)
            state = (*state[1:], nxt)
        return " ".join(words) or None
