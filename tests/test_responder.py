import random

from bot.db import Tag
from bot.markov import MarkovChain
from bot.brain import analyze
from bot.responder import blend, find_tag, make_insult, mode_weights, spice

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
    assert base["phrase"] == max(base.values())
    assert mode_weights(analyze("ок"))["short"] > base["short"]
    assert mode_weights(analyze("ВЫ ЧТО ТУТ ТВОРИТЕ"))["sponge"] > base["sponge"]
    assert mode_weights(analyze("а что вы думаете про это?"))["markov"] > base["markov"]
    sticker = mode_weights(analyze("", media="sticker"))
    assert sticker["sponge"] == 0 and sticker["sticker"] > base["sticker"]
    photo = mode_weights(analyze("", media="photo"), photo=True)
    assert photo["demotivator"] > 30
    assert min(base.values()) >= 0


def test_blend_glues_two_words():
    out = blend("пидорства", "база")
    assert out.startswith("пидор") and out.endswith("за")
    assert blend("кот", "пес")


def test_spice_keeps_word_count():
    chain = MarkovChain(2)
    chain.add("кибер котлета снова горит жёстко")
    rng = random.Random(1)
    for _ in range(50):
        assert len(spice("котлета снова горит", chain, rng).split()) == 3
