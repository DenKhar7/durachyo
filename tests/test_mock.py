import random

from bot import mock


def test_spongebob_alternates_case_and_keeps_text():
    out = mock.spongebob("привет, мир", random.Random(0))
    assert out.lower() == "привет, мир"
    letters = [c for c in out if c.isalpha()]
    assert all(a.isupper() != b.isupper() for a, b in zip(letters, letters[1:]))


def test_insult_contains_name_and_escapes_word():
    rng = random.Random(0)
    for _ in range(30):
        out = mock.insult("<a>Вася</a>", "<script>", rng)
        assert "<script>" not in out
        assert "Вася" in out


def test_insult_without_word_never_has_placeholder():
    rng = random.Random(1)
    for _ in range(30):
        assert "«»" not in mock.insult("Вася", None, rng)


def test_tagged_escapes_and_fills():
    out = mock.tagged("Зигор", "педофайл", "<b>", random.Random(0))
    assert "Зигор" in out and "педофайл" in out and "<b>" not in out
    assert "«»" not in mock.tagged("Зигор", "педофайл", None, random.Random(0))
