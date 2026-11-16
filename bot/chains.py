from bot.db import Database
from bot.markov import MarkovChain


class ChainStore:
    """One markov chain per chat, kept in memory and built from the db on first use.

    Old messages get trimmed from the db but can't be removed from a chain,
    so every rebuild_every new messages the chain is thrown away and built again.
    """

    def __init__(self, db: Database, order: int, rebuild_every: int = 500) -> None:
        self._db = db
        self._order = order
        self._rebuild_every = rebuild_every
        self._chains: dict[int, MarkovChain] = {}
        self._added: dict[int, int] = {}

    async def get(self, chat_id: int) -> MarkovChain:
        chain = self._chains.get(chat_id)
        if chain is None:
            chain = await self._build(chat_id)
            self._chains[chat_id] = chain
            self._added[chat_id] = 0
        return chain

    async def for_user(self, chat_id: int, user_id: int) -> MarkovChain:
        return await self._build(chat_id, user_id)

    async def learn(self, chat_id: int, text: str) -> None:
        chain = self._chains.get(chat_id)
        if chain is None:
            return
        chain.add(text)
        self._added[chat_id] += 1
        if self._added[chat_id] >= self._rebuild_every:
            self.invalidate(chat_id)

    def invalidate(self, chat_id: int) -> None:
        self._chains.pop(chat_id, None)
        self._added.pop(chat_id, None)

    async def _build(self, chat_id: int, user_id: int | None = None) -> MarkovChain:
        chain = MarkovChain(self._order)
        for text in await self._db.texts(chat_id, user_id):
            chain.add(text)
        return chain
