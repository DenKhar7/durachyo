import random

from bot.db import Tag
from bot.markov import MarkovChain
from bot.brain import analyze
from bot.responder import find_tag, make_insult, mode_weights

TAGS = [Tag("зигор", "Зигор", "педофайл"), Tag("егор", "Егор", "педофайл")]


def test_find_tag_matches_name_and_endings():
    assert find_tag("ну Зигор опять", TAGS).name == "Зигор"
    assert find_tag("спроси у Егора!", TAGS).name == "Егор"
    assert find_tag("ЕГОРУ привет", TAGS).name == "Егор"


def test_find_tag_ignores_unrelated_words():
    assert find_tag("пригорело", TAGS) is None
    assert find_tag("егоркинский район", TAGS) is None
    assert find_tag("", TAGS) is None


def test_make_insult_uses_chat_words():
    chain = MarkovChain(2)
    for text in ["кибер котлета снова горит", "кибер котлета опять лагает", "жёлтый тапок горит"]:
        chain.add(text)
    vocab = set(chain.vocabulary())
    rng = random.Random(0)
    for _ in range(30):
        out = make_insult("Вася", chain, rng, chat_share=1.0)
        assert "Вася" in out
        assert any(w in out for w in vocab)


def test_make_insult_on_empty_chain_falls_back():
    out = make_insult("Вася", MarkovChain(2), random.Random(0))
    assert "Вася" in out and "{" not in out


def test_mode_weights_follow_context():
    base = mode_weights(analyze("обычное сообщение средней длины"))
    short = mode_weights(analyze("ок"))
    assert short["free"] > short["seeded"]
    assert mode_weights(analyze("ВЫ ЧТО ТУТ ТВОРИТЕ"))["sponge"] > base["sponge"]
    assert mode_weights(analyze("а что вы думаете про это?"))["seeded"] > base["seeded"]
    assert min(short.values()) >= 1
