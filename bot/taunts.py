"""Text templates for taunts: insults, labels, spongebob case."""

import html
import random

ADJECTIVES = (
    "раковый",
    "токсичный",
    "криворукий",
    "безрукий",
    "лагающий",
    "донатный",
    "афкшный",
    "контуженный",
    "недоделанный",
    "протухший",
    "картонный",
    "дешёвый",
    "бракованный",
    "забаненный",
    "поехавший",
    "отбитый",
    "немытый",
    "пиксельный",
    "китайский",
    "бесплатный",
)
NOUNS = (
    "нуб",
    "рак",
    "бот",
    "фидер",
    "школьник",
    "донатер",
    "нпс",
    "тиммейт-балласт",
    "лоутаб",
    "чмоня",
    "лошара",
    "дегенерат",
    "клоун",
    "огрызок",
    "пельмень",
    "таракан",
    "овощ",
    "мамкин тащер",
    "крип",
    "читер",
    "нубяра",
    "дед инсайд",
    "пикми",
    "кабачок",
)
INSULTS = (
    "{name}, ты {adj} {noun}.",
    "{name}, {adj} {noun}, удали доту и иди потрогай траву.",
    "{name}, у тебя K/D как у бота на изи. То есть ноль.",
    "{name}, даже боты на изи играют лучше тебя.",
    "{name}, твой IQ меньше пинга до Австралии.",
    "{name}, мама звонила, сказала что ты {adj} {noun} и обед стынет.",
    "Если бы {adj} {noun} умел печатать, его звали бы {name}.",
    "{name}, ты как «{word}»: никто не понял, но всем противно.",
    "{name}, у тебя в голове одно слово, и это «{word}».",
    "{name}, о боже мой, они убили Кенни! А, нет, это просто {name} опять написал «{word}».",
    "{name}, я не толстый, у меня кость широкая. А ты просто {adj} {noun}.",
    "Уважай мой авторитет, {name}! Ты {adj} {noun}.",
    "Да пошли вы, ребята, я домой. А ты, {name}, особенно, {adj} {noun}.",
    "{name}, тебя даже в ранкед с ботами не берут.",
    "{name}, GG, репорт за руины. Ты {adj} {noun}.",
    "{name}, ты как «{word}», только ещё тупее.",
    "{name}, иди донать дальше, {adj} {noun}.",
    "Учёные до сих пор не поняли, зачем {name} пишет в этот чат.",
    "{name} - живое доказательство, что эволюция иногда идёт назад.",
    "{name}, тебя родители на респавне забыли.",
)
CHAT_INSULTS = (
    "{name}, ты {adj} {word}.",
    "{name}, ты как «{phrase}»: никто не понял, но всем противно.",
    "{name}, у тебя в голове одно: «{phrase}».",
    "{name} опять за своё: «{phrase}».",
    "{name}, «{phrase}» - это про тебя.",
    "{name}, иди {word} потрогай.",
    "{name}, {adj} {word}, вот ты кто.",
    "Чат, кто тут самый {adj}? Правильно, {name}.",
    "{name}, мы все помним твоё «{phrase}».",
    "{name}, ещё раз напишешь и я расскажу всем про «{phrase}».",
)
TAGGED = (
    "А ну да, {name} тот ещё {tag} по «{word}».",
    "{name}? Это который {tag}? Ну да, ну да, особенно по «{word}».",
    "Кстати, {name} - {tag}. Источник: «{word}».",
    "Опять {name}... {tag} со стажем, эксперт по «{word}».",
    "Пацаны, {name} же {tag}, все знают. Даже «{word}» знает.",
    "{name} - {tag}, и это не обсуждается. Доказательство: «{word}».",
)
TAGGED_NO_WORD = (
    "А ну да, {name} тот ещё {tag}.",
    "{name}? Это который {tag}? Ну да, ну да.",
    "Пацаны, {name} же {tag}, все знают.",
)


def spongebob(text: str, rng: random.Random) -> str:
    """пОвТоРяЕт С кРиВлЯнИеМ."""
    upper = rng.random() < 0.5
    out = []
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)


def insult(name_html: str, word: str | None, rng: random.Random) -> str:
    """Stock insult; templates with a chat word are used only when there is a word."""
    templates = INSULTS if word else tuple(t for t in INSULTS if "{word}" not in t)
    return rng.choice(templates).format(
        name=name_html,
        adj=rng.choice(ADJECTIVES),
        noun=rng.choice(NOUNS),
        word=html.escape(word or ""),
    )


def chat_insult(name_html: str, phrase: str, word: str, adj: str, rng: random.Random) -> str:
    """Insult assembled from the chat's own vocabulary."""
    return rng.choice(CHAT_INSULTS).format(
        name=name_html, phrase=html.escape(phrase), word=html.escape(word), adj=html.escape(adj)
    )


def tagged(name: str, tag: str, word: str | None, rng: random.Random) -> str:
    """Reply for a /tag label: «А ну да, Зигор тот ещё ...»."""
    templates = TAGGED if word else TAGGED_NO_WORD
    return rng.choice(templates).format(
        name=html.escape(name), tag=html.escape(tag), word=html.escape(word or "")
    )
