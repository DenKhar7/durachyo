"""Everything handlers need, in one object. aiogram passes it in as `app`."""

import random
from dataclasses import dataclass, field
from typing import Self

from aiogram import Bot
from aiogram.types import User

from bot.brain import Brain
from bot.chains import ChainStore
from bot.config import Settings
from bot.daily import Quiz
from bot.db import Database
from bot.utils import Cooldown, RateLimit

NICK_COOLDOWN = 30.0
WHO_COOLDOWN = 3.0


@dataclass(slots=True)
class Cooldowns:
    reply: Cooldown
    command: Cooldown
    everyone: Cooldown
    duel: RateLimit
    nick: Cooldown = field(default_factory=lambda: Cooldown(NICK_COOLDOWN))
    who: Cooldown = field(default_factory=lambda: Cooldown(WHO_COOLDOWN))
    # 15th message within 2 minutes = spammer
    spam: RateLimit = field(default_factory=lambda: RateLimit(14, 120))

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            reply=Cooldown(settings.reply_cooldown),
            command=Cooldown(settings.command_cooldown),
            everyone=Cooldown(settings.all_cooldown),
            duel=RateLimit(settings.duels_per_minute, 60),
        )


@dataclass(slots=True)
class App:
    settings: Settings
    bot: Bot
    db: Database
    me: User
    chains: ChainStore
    cooldowns: Cooldowns
    brain: Brain = field(default_factory=Brain)
    rng: random.Random = field(default_factory=random.Random)
    # open «кто это сказал» quizzes by (chat_id, message_id); lost on restart, that's fine
    quizzes: dict[tuple[int, int], Quiz] = field(default_factory=dict)

    @classmethod
    def create(cls, settings: Settings, bot: Bot, db: Database, me: User) -> Self:
        return cls(
            settings=settings,
            bot=bot,
            db=db,
            me=me,
            chains=ChainStore(db, settings.markov_order),
            cooldowns=Cooldowns.from_settings(settings),
        )
