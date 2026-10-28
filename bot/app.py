"""Shared state of the running bot. aiogram injects it into every handler as app."""

import random
from dataclasses import dataclass, field
from typing import Self

from aiogram import Bot
from aiogram.types import User

from bot.brain import Brain
from bot.chains import ChainStore
from bot.config import Settings
from bot.db import Database
from bot.utils import Cooldown

NICK_COOLDOWN = 30.0
WHO_COOLDOWN = 3.0


@dataclass(slots=True)
class Cooldowns:
    reply: Cooldown
    command: Cooldown
    everyone: Cooldown
    nick: Cooldown = field(default_factory=lambda: Cooldown(NICK_COOLDOWN))
    who: Cooldown = field(default_factory=lambda: Cooldown(WHO_COOLDOWN))

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            reply=Cooldown(settings.reply_cooldown),
            command=Cooldown(settings.command_cooldown),
            everyone=Cooldown(settings.all_cooldown),
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
