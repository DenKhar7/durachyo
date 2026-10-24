import random

from bot.brain import Brain, analyze


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def chatter(brain: Brain, n: int) -> None:
    for _ in range(n):
        brain.observe(-1)


def test_analyze():
    ctx = analyze("ЧТО ЗА ДИЧЬ?")
    assert ctx.question and ctx.shouting and ctx.words == 3
    assert not analyze("ок").shouting


def test_addressed_always_and_zero_mutes():
    brain = Brain()
    chatter(brain, 1)
    assert brain.reply_probability(-1, analyze("эй", addressed=True), 0) == 100
    assert brain.reply_probability(-1, analyze("обычный текст тут"), 0) == 0


def test_backs_off_after_speaking_and_warms_up_in_silence():
    brain = Brain()
    ctx = analyze("ну и что мы будем делать вечером")
    brain.spoke(-1)
    chatter(brain, 1)
    right_after = brain.reply_probability(-1, ctx, 40)
    chatter(brain, 12)
    later = brain.reply_probability(-1, ctx, 40)
    assert right_after < 20 < later


def test_tags_and_questions_raise_interest():
    brain = Brain()
    chatter(brain, 5)
    plain = brain.reply_probability(-1, analyze("пошли в доту сегодня"), 30)
    assert brain.reply_probability(-1, analyze("пошли в доту сегодня?"), 30) > plain
    assert brain.reply_probability(-1, analyze("пошли в доту сегодня", tagged=True), 30) > plain


def test_should_reply_is_random_but_bounded():
    brain = Brain()
    chatter(brain, 5)
    rng = random.Random(0)
    hits = sum(brain.should_reply(-1, analyze("какой-то средний текст"), 40, rng) for _ in range(1000))
    assert 250 < hits < 550


def test_needs_revive_once_per_silence():
    clock = Clock()
    brain = Brain(clock)
    assert not brain.needs_revive(-1, 3600)
    brain.observe(-1)
    clock.t += 1800
    assert not brain.needs_revive(-1, 3600)
    clock.t += 3600
    assert brain.needs_revive(-1, 3600)
    brain.spoke(-1)
    clock.t += 99999
    assert not brain.needs_revive(-1, 3600)
    assert not brain.needs_revive(-1, 0)


def test_called_chance_and_media_skip_word_penalty():
    brain = Brain()
    chatter(brain, 5)
    assert brain.reply_probability(-1, analyze("сглыпа", addressed=True), 40, called_chance=80) == 80
    assert brain.reply_probability(-1, analyze("", media="sticker"), 40) > brain.reply_probability(-1, analyze(""), 40)


def test_memory_of_recent_and_own_lines():
    brain = Brain()
    state = brain.observe(-1, "привет")
    brain.observe(-1)
    assert list(state.recent) == ["привет"]
    brain.spoke(-1, "Normalno", 42)
    assert state.last_bot_plain == "Normalno" and state.last_bot_id == 42
    assert not state.scored and "normalno" in state.recent_bot
