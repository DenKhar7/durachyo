import random

import pytest

from bot.markov import MarkovChain, normalize

CORPUS = ["я люблю пиво", "я люблю спать днём", "пиво это жизнь", "днём я сплю"]


def make(order: int = 2) -> MarkovChain:
    chain = MarkovChain(order)
    for text in CORPUS:
        chain.add(text)
    return chain


def test_empty_chain_generates_nothing():
    assert MarkovChain().generate() is None


def test_generates_only_known_words():
    chain, rng = make(), random.Random(1)
    vocab = {w for t in CORPUS for w in t.split()}
    for _ in range(50):
        out = chain.generate(rng=rng)
        assert out and set(out.split()) <= vocab


def test_seeded_generation_contains_seed():
    chain, rng = make(), random.Random(2)
    for _ in range(20):
        out = chain.generate("Пиво!", rng=rng)
        assert "пиво" in {normalize(w) for w in out.split()}


def test_unknown_seed_returns_none():
    assert make().generate("водка") is None


def test_max_words_respected():
    chain = MarkovChain(1)
    chain.add(" ".join(["бла"] * 200))
    assert len(chain.generate(max_words=10).split()) <= 10


def test_order_one_mixes_sentences():
    chain, rng = make(order=1), random.Random(3)
    outputs = {chain.generate(rng=rng) for _ in range(200)}
    assert outputs - set(CORPUS)


def test_known_and_normalize():
    chain = make()
    assert normalize("«Пиво»!!") == "пиво"
    assert chain.known("ПИВО,") and not chain.known("...")


def test_frequency_counts_normalized_words():
    chain = make()
    assert chain.frequency("Я") == 3
    assert chain.frequency("пиво!") == 2
    assert chain.frequency("водка") == 0


def test_invalid_order():
    with pytest.raises(ValueError):
        MarkovChain(0)
