import html
import random

ADJECTIVES = (
    "кринжовый", "душный", "бесячий", "токсичный", "унылый", "криворукий", "картонный",
    "протухший", "невменяемый", "контуженный", "заплесневелый", "недоделанный", "лысый",
)
NOUNS = (
    "пельмень", "душнила", "клоун", "огрызок", "валенок", "таракан", "нпс", "овощ",
    "тапок", "чебурек", "пень", "кабачок", "сухарик", "голубь",
)
INSULTS = (
    "{name}, ты {adj} {noun}.",
    "{name}, {adj} {noun}, иди потрогай траву.",
    "Учёные до сих пор не поняли, зачем {name} пишет в этот чат.",
    "{name}, твой IQ ниже комнатной температуры.",
    "{name}, ты как «{word}» — никто не понял, но всем неприятно.",
    "Если бы {adj} {noun} умел печатать, его звали бы {name}.",
    "{name}, мама звонила, сказала что ты {adj} {noun}.",
    "{name}, у тебя в голове одно слово, и это «{word}».",
)
QUOTES = (
    "{name} когда-то выдал: «{quote}»",
    "Напоминаю, {name} писал(а): «{quote}»",
    "«{quote}» © {name}, великий мыслитель",
    "{name}, а помнишь, как ты сказал(а) «{quote}»? Я помню. Я всё помню.",
    "Цитаты великих людей. {name}: «{quote}»",
)


def spongebob(text: str, rng: random.Random | None = None) -> str:
    upper = (rng or random).random() < 0.5
    out = []
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)


def insult(name_html: str, word: str | None = None, rng: random.Random | None = None) -> str:
    rng = rng or random
    templates = INSULTS if word else tuple(t for t in INSULTS if "{word}" not in t)
    return rng.choice(templates).format(
        name=name_html,
        adj=rng.choice(ADJECTIVES),
        noun=rng.choice(NOUNS),
        word=html.escape(word or ""),
    )


def quote_back(name_html: str, quote: str, rng: random.Random | None = None) -> str:
    return (rng or random).choice(QUOTES).format(name=name_html, quote=html.escape(quote))
