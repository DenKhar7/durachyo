from dataclasses import dataclass
from pathlib import Path

import aiosqlite

_NOW = "CAST(strftime('%s', 'now') AS INTEGER)"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    created_at INTEGER NOT NULL DEFAULT ({_NOW})
);
CREATE INDEX IF NOT EXISTS ix_messages_chat ON messages (chat_id, id);
CREATE INDEX IF NOT EXISTS ix_messages_chat_user ON messages (chat_id, user_id);

CREATE TABLE IF NOT EXISTS users (
    chat_id   INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    full_name TEXT    NOT NULL,
    username  TEXT,
    last_seen INTEGER NOT NULL DEFAULT ({_NOW}),
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS tags (
    chat_id INTEGER NOT NULL,
    key     TEXT    NOT NULL,
    name    TEXT    NOT NULL,
    label   TEXT    NOT NULL,
    PRIMARY KEY (chat_id, key)
);

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id      INTEGER PRIMARY KEY,
    reply_chance INTEGER NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class KnownUser:
    user_id: int
    full_name: str
    username: str | None = None


@dataclass(frozen=True, slots=True)
class Tag:
    key: str
    name: str
    label: str


class Database:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @classmethod
    async def open(cls, path: Path | str) -> "Database":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    async def add_message(self, chat_id: int, user_id: int, text: str, keep: int) -> None:
        await self._conn.execute(
            "INSERT INTO messages (chat_id, user_id, text) VALUES (?, ?, ?)",
            (chat_id, user_id, text),
        )
        await self._conn.execute(
            """DELETE FROM messages WHERE chat_id = ? AND id <= (
                   SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1 OFFSET ?
               )""",
            (chat_id, chat_id, keep),
        )
        await self._conn.commit()

    async def texts(self, chat_id: int, user_id: int | None = None) -> list[str]:
        if user_id is None:
            query, args = "SELECT text FROM messages WHERE chat_id = ? ORDER BY id", (chat_id,)
        else:
            query = "SELECT text FROM messages WHERE chat_id = ? AND user_id = ? ORDER BY id"
            args = (chat_id, user_id)
        async with self._conn.execute(query, args) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def random_message(self, chat_id: int, user_id: int | None = None) -> tuple[int, str] | None:
        if user_id is None:
            query, args = "SELECT user_id, text FROM messages WHERE chat_id = ?", (chat_id,)
        else:
            query = "SELECT user_id, text FROM messages WHERE chat_id = ? AND user_id = ?"
            args = (chat_id, user_id)
        async with self._conn.execute(query + " ORDER BY RANDOM() LIMIT 1", args) as cur:
            row = await cur.fetchone()
        return (row[0], row[1]) if row else None

    async def upsert_user(self, chat_id: int, user_id: int, full_name: str, username: str | None) -> None:
        await self._conn.execute(
            f"""INSERT INTO users (chat_id, user_id, full_name, username, last_seen)
                VALUES (?, ?, ?, ?, {_NOW})
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username  = excluded.username,
                    last_seen = excluded.last_seen""",
            (chat_id, user_id, full_name, username),
        )
        await self._conn.commit()

    async def get_user(self, chat_id: int, user_id: int) -> KnownUser | None:
        return await self._one_user(
            "SELECT user_id, full_name, username FROM users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )

    async def find_user_by_username(self, chat_id: int, username: str) -> KnownUser | None:
        return await self._one_user(
            "SELECT user_id, full_name, username FROM users WHERE chat_id = ? AND username = ? COLLATE NOCASE",
            (chat_id, username),
        )

    async def random_user(self, chat_id: int) -> KnownUser | None:
        return await self._one_user(
            "SELECT user_id, full_name, username FROM users WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1",
            (chat_id,),
        )

    async def users(self, chat_id: int) -> list[KnownUser]:
        async with self._conn.execute(
            "SELECT user_id, full_name, username FROM users WHERE chat_id = ? ORDER BY last_seen DESC",
            (chat_id,),
        ) as cur:
            return [KnownUser(*row) for row in await cur.fetchall()]

    async def reply_chance(self, chat_id: int, default: int) -> int:
        async with self._conn.execute(
            "SELECT reply_chance FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else default

    async def set_reply_chance(self, chat_id: int, value: int) -> None:
        await self._conn.execute(
            """INSERT INTO chat_settings (chat_id, reply_chance) VALUES (?, ?)
               ON CONFLICT (chat_id) DO UPDATE SET reply_chance = excluded.reply_chance""",
            (chat_id, value),
        )
        await self._conn.commit()

    async def forget_user(self, chat_id: int, user_id: int) -> int:
        cur = await self._conn.execute(
            "DELETE FROM messages WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        deleted = cur.rowcount
        await self._conn.execute("DELETE FROM users WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await self._conn.commit()
        return deleted

    async def stats(self, chat_id: int) -> tuple[int, int]:
        async with self._conn.execute(
            """SELECT (SELECT COUNT(*) FROM messages WHERE chat_id = ?),
                      (SELECT COUNT(*) FROM users WHERE chat_id = ?)""",
            (chat_id, chat_id),
        ) as cur:
            row = await cur.fetchone()
        return row[0], row[1]

    async def set_tag(self, chat_id: int, key: str, name: str, label: str) -> None:
        await self._conn.execute(
            """INSERT INTO tags (chat_id, key, name, label) VALUES (?, ?, ?, ?)
               ON CONFLICT (chat_id, key) DO UPDATE SET name = excluded.name, label = excluded.label""",
            (chat_id, key, name, label),
        )
        await self._conn.commit()

    async def delete_tag(self, chat_id: int, key: str) -> bool:
        cur = await self._conn.execute("DELETE FROM tags WHERE chat_id = ? AND key = ?", (chat_id, key))
        await self._conn.commit()
        return cur.rowcount > 0

    async def tags(self, chat_id: int) -> list[Tag]:
        async with self._conn.execute(
            "SELECT key, name, label FROM tags WHERE chat_id = ? ORDER BY key", (chat_id,)
        ) as cur:
            return [Tag(*row) for row in await cur.fetchall()]

    async def _one_user(self, query: str, args: tuple) -> KnownUser | None:
        async with self._conn.execute(query, args) as cur:
            row = await cur.fetchone()
        return KnownUser(*row) if row else None
