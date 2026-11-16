"""Дуэли: оба бросают d20, у кого больше - тот и отхуярил"""

import random
from dataclasses import dataclass

SIDES = 20
HOT_STREAK = 2  # from this many wins in a row the bot starts bragging about it

WIN_LINES = (
    "{winner} напал и отхуярил {loser}",
    "{loser} получил пиздов от {winner}",
    "{winner} уложил {loser} одним яйцом",
    "{winner} вписал {loser} леща",
    "{loser} кинул Юми в {winner}",
    "{winner} разобрал {loser} на лего",
    "{loser} опростафилакокился и {winner} нет",
    "{winner} бросил лего в {loser}",
    "{loser} был растоптан Зюзиком и {winner}",
    "{winner} отправил {loser} на фонтан",
    "{winner} отвёл {loser} в кино",
    "{loser} сыканул и {winner} зачилилось",
)
CRIT_LINES = (
    "КРИТ! {winner} позвал Мункека и тот усыыпил {loser} и тот скончался",
    "КРИТ! {winner} сломал {loser} самооценку, кек",
    "КРИТ! {loser} наступил на лего, {winner} его рассыпал",
)
FUMBLE_LINES = (
    "{loser} споткнулся и отхуярил сам себя. Изичная для {winner}",
    "{loser} пропало на ДнД с Владом",
)
DRAW_LINES = (
    "Ничья: {a} и {b} напились и спатьц",
    "{a} и {b} закурили кальянчик",
    "{a} и {b} ушли играть в ДнД",
)


@dataclass(frozen=True, slots=True)
class Fight:
    roll_a: int
    roll_b: int

    @property
    def a_won(self) -> bool | None:
        """None is a draw"""
        if self.roll_a == self.roll_b:
            return None
        return self.roll_a > self.roll_b


def fight(rng: random.Random) -> Fight:
    return Fight(rng.randint(1, SIDES), rng.randint(1, SIDES))


def fight_line(result: Fight, a: str, b: str, rng: random.Random) -> str:
    """a and b are ready-to-send (already escaped) names."""
    if result.a_won is None:
        return rng.choice(DRAW_LINES).format(a=a, b=b)
    winner, loser, win_roll, lose_roll = (
        (a, b, result.roll_a, result.roll_b) if result.a_won else (b, a, result.roll_b, result.roll_a)
    )
    lines: tuple[str, ...]
    if win_roll == SIDES:
        lines = CRIT_LINES
    elif lose_roll == 1:
        lines = FUMBLE_LINES
    else:
        lines = WIN_LINES
    return rng.choice(lines).format(winner=winner, loser=loser)
