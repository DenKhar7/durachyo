import random
import re
from dataclasses import dataclass

from bot.markov import normalize

PIG = ("свинья", "псина")
PEDO = ("пдфайл", "лоликонщик", "лоли")
DIRTY_REACTIONS = ("🤡", "💩", "🗿")


@dataclass(frozen=True, slots=True)
class Nick:
    display: str | None
    pattern: re.Pattern[str]
    labels: tuple[str, ...]
    sep: str = "-"
    reactions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NickHit:
    nick: Nick
    name: str


def _p(regex: str) -> re.Pattern[str]:
    return re.compile(rf"^(?:{regex})$")


NICKS = (
    Nick("Маша", _p(r"маш(?:а|и|е|у|ей|ею|ка|ки|ке|ку|кой|енька|еньки|еньку|уля|ули|улю|улей)?|мань(?:ка|ки|ку|кой)|маня"), PIG, "-", DIRTY_REACTIONS),
    Nick("Лесон", _p(r"лесон(?:а|у|ом|е|ы|чик|чика|ушка|ушку|ыч)?"), PIG, "-", DIRTY_REACTIONS),
    Nick("Денис", _p(r"денис(?:а|у|ом|е|ы|ка|ки|ку|кой|очка|очку|ик|ика|ыч)?|ден(?:чик|чика|я|ю|ей)"), PIG, "-", DIRTY_REACTIONS),
    Nick("Егор", _p(r"ег[оа]р(?:а|у|ом|е|ы|ка|ки|ку|кой|ушка|ушку|ик|ика|чик|ыч|ов|ам)?"), PEDO, "="),
    Nick(None, _p(r"(?P<base>зиг(?:[ао]г)?[оа]р)(?:а|у|ом|е|ы|ка|ик|чик|ыч)?"), PEDO, "="),
)


def find_nick(text: str) -> NickHit | None:
    """display=None keeps the name the way it was written (Зигор, Зигагор, Зигогор), without the case ending."""
    for word in text.split():
        key = normalize(word)
        for nick in NICKS:
            m = nick.pattern.match(key)
            if m:
                name = nick.display or m.group("base").capitalize()
                return NickHit(nick, name)
    return None


def nick_line(hit: NickHit, rng: random.Random) -> str:
    return f"{hit.name} {hit.nick.sep} {rng.choice(hit.nick.labels)}"
