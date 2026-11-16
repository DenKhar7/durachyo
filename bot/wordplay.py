import random

from bot import taunts
from bot.markov import MarkovChain, normalize

SPICE_CHANCE = 0.2
INSULT_CHAT_SHARE = 0.8
# good enough to guess an adjective, nobody is going to pull in pymorphy for this
ADJ_ENDINGS = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие")
_VOWELS = frozenset("аеёиоуыэюяaeiouy")


def blend(a: str, b: str) -> str:
    """Head of a + tail of b, cut after/before a vowel: пидорства + база -> пидорза."""
    cut_a = next((i + 1 for i in range(len(a) // 2, len(a)) if a[i] in _VOWELS), len(a) // 2 + 1)
    cut_b = next((i for i in range(len(b) // 2, 0, -1) if b[i] in _VOWELS), len(b) // 2)
    return a[:cut_a] + b[cut_b:]


def spice(text: str, chain: MarkovChain, rng: random.Random) -> str:
    """Once in a while swaps one word for a mash-up with another word from the chat."""
    words = text.split()
    slots = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha()]
    vocab = [w for w in chain.vocabulary() if len(w) >= 4 and w.isalpha()]
    if not slots or len(vocab) < 2 or rng.random() >= SPICE_CHANCE:
        return text
    i = rng.choice(slots)
    other = rng.choice([w for w in vocab if w != words[i].lower()] or vocab)
    words[i] = blend(words[i], other) if rng.random() < 0.5 else blend(other, words[i])
    return " ".join(words)


def make_insult(
    name_html: str, chain: MarkovChain, rng: random.Random, chat_share: float = INSULT_CHAT_SHARE
) -> str:
    """Insult made of the chat's own words. Falls back to the canned ones when there's nothing to use."""
    vocab = [w for w in chain.vocabulary() if 3 <= len(w) <= 16 and not w.isdigit()]
    phrase = chain.generate(rng.choice(vocab), max_words=6, rng=rng) if vocab else None
    if not vocab or not phrase or rng.random() >= chat_share:
        return taunts.insult(name_html, rng.choice(vocab) if vocab else None, rng)
    adjectives = [w for w in vocab if len(w) >= 5 and w.endswith(ADJ_ENDINGS)]
    adj = rng.choice(adjectives) if adjectives else rng.choice(taunts.ADJECTIVES)
    nouns = [w for w in vocab if len(w) >= 4 and w not in adjectives]
    return taunts.chat_insult(name_html, phrase, rng.choice(nouns or vocab), adj, rng)


def rare_words(text: str, chain: MarkovChain, rng: random.Random, n: int = 3) -> list[str]:
    """The rarest words of the text that the chat knows.

    A reply built around a rare word looks on topic. Around "это" or "что" it doesn't.
    """
    unique = {normalize(w) for w in text.split() if len(normalize(w)) >= 4 and chain.known(w)}
    return sorted(unique, key=lambda k: (chain.frequency(k), rng.random()))[:n]
