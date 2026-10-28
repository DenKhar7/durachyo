import random

from bot.markov import MarkovChain
from bot.wordplay import blend, make_insult, rare_words, spice


def test_blend_glues_two_words() -> None:
    out = blend("пидорства", "база")
    assert out.startswith("пидор") and out.endswith("за")
    assert blend("кот", "пес")


def test_spice_keeps_word_count() -> None:
    chain = MarkovChain(2)
    chain.add("кибер котлета снова горит жёстко")
    rng = random.Random(1)
    for _ in range(50):
        assert len(spice("котлета снова горит", chain, rng).split()) == 3


def test_make_insult_uses_chat_words() -> None:
    chain = MarkovChain(2)
    for text in ["кибер котлета снова горит", "кибер котлета опять лагает", "жёлтый тапок горит"]:
        chain.add(text)
    vocab = set(chain.vocabulary())
    rng = random.Random(0)
    for _ in range(30):
        out = make_insult("Вася", chain, rng, chat_share=1.0)
        assert "Вася" in out
        assert any(w in out for w in vocab)


def test_make_insult_on_empty_chain_falls_back() -> None:
    out = make_insult("Вася", MarkovChain(2), random.Random(0))
    assert "Вася" in out and "{" not in out


def test_rare_words_prefers_rare_known_words() -> None:
    chain = MarkovChain(2)
    for text in ["пиво пиво пиво тут", "пиво дома", "холодное пиво"]:
        chain.add(text)
    assert rare_words("а холодное пиво есть водка", chain, random.Random(0)) == ["холодное", "пиво"]
