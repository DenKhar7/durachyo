from bot.app import App
from bot.brain import analyze
from bot.responder import ReplyMode, build_reply, mode_weights
from tests.helpers import CHAT, make_message

CORPUS = ["го в доту", "го", "база", "пиво холодное есть?", "я пью пиво дома", "мы пьём пиво на улице"]


def test_mode_weights_follow_context() -> None:
    base = mode_weights(analyze("обычное сообщение средней длины"))
    assert base[ReplyMode.PHRASE] == max(base.values())
    assert mode_weights(analyze("ок"))[ReplyMode.SHORT] > base[ReplyMode.SHORT]
    assert mode_weights(analyze("ВЫ ЧТО ТУТ ТВОРИТЕ"))[ReplyMode.SPONGE] > base[ReplyMode.SPONGE]
    assert mode_weights(analyze("а что вы думаете про это?"))[ReplyMode.MARKOV] > base[ReplyMode.MARKOV]
    sticker = mode_weights(analyze("", media="sticker"))
    assert sticker[ReplyMode.SPONGE] == 0 and sticker[ReplyMode.STICKER] > base[ReplyMode.STICKER]
    assert mode_weights(analyze("", media="photo"), photo=True)[ReplyMode.DEMOTIVATOR] > 30
    assert min(base.values()) >= 0


async def test_build_reply_always_answers_with_chat_material(app: App) -> None:
    for text in CORPUS * 5:
        await app.db.add_message(CHAT, 10, text, keep=1000)
    message = make_message("кто пиво будет?")
    state = app.brain.observe(CHAT, message.text)
    modes = set()
    for _ in range(40):
        reply = await build_reply(message, analyze(message.text or ""), app, state=state)
        assert reply is not None and reply.text and "{" not in reply.text
        modes.add(reply.mode)
    assert len(modes) >= 3


async def test_build_reply_uses_tag(app: App) -> None:
    await app.db.add_message(CHAT, 10, "зигор опять тут", keep=100)
    app.settings = app.settings.model_copy(update={"tag_chance": 100})
    message = make_message("где зигор")
    tags = await app.db.tags(CHAT)
    assert not tags
    await app.db.set_tag(CHAT, "зигор", "Зигор", "нуб")
    (tag,) = await app.db.tags(CHAT)
    state = app.brain.observe(CHAT, message.text)
    reply = await build_reply(message, analyze("где зигор", tagged=True), app, state=state, tag=tag)
    assert reply is not None and reply.mode is ReplyMode.TAG
    assert reply.text and "Зигор" in reply.text and "нуб" in reply.text
