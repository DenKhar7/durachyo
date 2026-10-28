from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import aiosqlite

_NOW = "CAST(strftime('%s', 'now') AS INTEGER)"
_SPACES = "(length(trim(text)) - length(replace(trim(text), ' ', '')))"
_BEFORE_RECENT = "id <= (SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1 OFFSET ?)"


def _lower(value: str | None) -> str | None:
    """SQLite's lower() only knows ASCII; this one lowers Cyrillic too."""
    return value.lower() if value is not None else None


def _escape_like(value: str) -> str:
    """Makes % and _ in user text literal for LIKE ... ESCAPE '!'."""
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


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

CREATE TABLE IF NOT EXISTS media (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    kind    TEXT    NOT NULL,
    uid     TEXT    NOT NULL,
    file_id TEXT    NOT NULL,
    emoji   TEXT,
    UNIQUE (chat_id, uid)
);
CREATE INDEX IF NOT EXISTS ix_media_chat_kind ON media (chat_id, kind, id);

CREATE TABLE IF NOT EXISTS hits (
    chat_id INTEGER NOT NULL,
    text    TEXT    NOT NULL,
    score   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, text)
);

CREATE TABLE IF NOT EXISTS toad_memes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,  -- NULL: from the internet, shared by all chats
    kind    TEXT    NOT NULL,  -- photo / animation / sticker
    source  TEXT    NOT NULL,  -- subreddit or "chat"
    url     TEXT,
    file_id TEXT,  -- Telegram's copy, filled after the first send
    uid     TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS toad_days (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    day     TEXT    NOT NULL,
    meme_id INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id, day)
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


@dataclass(frozen=True, slots=True)
class ToadMeme:
    id: int
    kind: str
    source: str
    url: str | None
    file_id: str | None


_TOAD = "SELECT m.id, m.kind, m.source, m.url, m.file_id FROM toad_memes m"


class Database:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @classmethod
    async def open(cls, path: Path | str) -> "Database":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        await conn.create_function("pylower", 1, _lower, deterministic=True)
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
        query = "SELECT text FROM messages WHERE chat_id = ?"
        args: list[object] = [chat_id]
        if user_id is not None:
            query += " AND user_id = ?"
            args.append(user_id)
        async with self._conn.execute(query + " ORDER BY id", args) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def old_phrase(
        self,
        chat_id: int,
        skip_recent: int,
        *,
        word: str | None = None,
        min_words: int = 2,
        max_words: int = 12,
    ) -> str | None:
        """Random message older than the newest skip_recent ones.

        With word: only messages containing it, case-insensitive.
        """
        # only module constants are interpolated, user values go through ? placeholders
        query = (
            f"SELECT text FROM messages WHERE chat_id = ? AND {_BEFORE_RECENT} AND {_SPACES} BETWEEN ? AND ?"  # noqa: S608
        )
        args: list[object] = [chat_id, chat_id, skip_recent, min_words - 1, max_words - 1]
        if word:
            query += " AND pylower(text) LIKE ? ESCAPE '!'"
            args.append(f"%{_escape_like(word.lower())}%")
        async with self._conn.execute(query + " ORDER BY RANDOM() LIMIT 1", args) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def short_phrases(
        self, chat_id: int, limit: int = 150, min_count: int = 2
    ) -> list[tuple[str, int]]:
        """The chat's own go-to replies: messages of up to 3 words that people keep repeating."""
        async with self._conn.execute(
            f"""SELECT pylower(trim(text)) AS t, COUNT(*) AS n FROM messages
                WHERE chat_id = ? AND length(text) <= 30 AND {_SPACES} <= 2
                GROUP BY t HAVING n >= ? ORDER BY n DESC LIMIT ?""",  # noqa: S608
            (chat_id, min_count, limit),
        ) as cur:
            return [(row[0], row[1]) for row in await cur.fetchall()]

    async def add_media(
        self, chat_id: int, kind: str, uid: str, file_id: str, *, emoji: str | None = None, keep: int = 500
    ) -> None:
        """Remembers a sticker/gif/photo by its unique id, keeping the newest keep of each kind."""
        await self._conn.execute(
            """INSERT INTO media (chat_id, kind, uid, file_id, emoji) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (chat_id, uid) DO UPDATE SET file_id = excluded.file_id""",
            (chat_id, kind, uid, file_id, emoji),
        )
        await self._conn.execute(
            """DELETE FROM media WHERE chat_id = ? AND kind = ? AND id <= (
                   SELECT id FROM media WHERE chat_id = ? AND kind = ? ORDER BY id DESC LIMIT 1 OFFSET ?
               )""",
            (chat_id, kind, chat_id, kind, keep),
        )
        await self._conn.commit()

    async def random_media(self, chat_id: int, kind: str) -> str | None:
        async with self._conn.execute(
            "SELECT file_id FROM media WHERE chat_id = ? AND kind = ? ORDER BY RANDOM() LIMIT 1",
            (chat_id, kind),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def add_hit(self, chat_id: int, text: str) -> None:
        await self._conn.execute(
            """INSERT INTO hits (chat_id, text, score) VALUES (?, ?, 1)
               ON CONFLICT (chat_id, text) DO UPDATE SET score = score + 1""",
            (chat_id, text),
        )
        await self._conn.commit()

    async def hits(self, chat_id: int, limit: int = 50) -> list[tuple[str, int]]:
        async with self._conn.execute(
            "SELECT text, score FROM hits WHERE chat_id = ? ORDER BY score DESC LIMIT ?", (chat_id, limit)
        ) as cur:
            return [(row[0], row[1]) for row in await cur.fetchall()]

    async def upsert_user(self, chat_id: int, user_id: int, full_name: str, username: str | None) -> None:
        await self._conn.execute(
            f"""INSERT INTO users (chat_id, user_id, full_name, username, last_seen)
                VALUES (?, ?, ?, ?, {_NOW})
                ON CONFLICT (chat_id, user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username  = excluded.username,
                    last_seen = excluded.last_seen""",  # noqa: S608
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
            "SELECT user_id, full_name, username FROM users"
            " WHERE chat_id = ? AND username = ? COLLATE NOCASE",
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
        return (row[0], row[1]) if row else (0, 0)

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

    async def add_toad_memes(self, links: Sequence[tuple[str, str, str]]) -> int:
        """Shared memes from the internet as (kind, source, url); known urls are skipped."""
        before = self._conn.total_changes
        await self._conn.executemany(
            "INSERT OR IGNORE INTO toad_memes (chat_id, kind, source, url, uid) VALUES (NULL, ?, ?, ?, ?)",
            [(kind, source, url, url) for kind, source, url in links],
        )
        await self._conn.commit()
        return self._conn.total_changes - before

    async def add_chat_toad(self, chat_id: int, kind: str, uid: str, file_id: str) -> bool:
        cur = await self._conn.execute(
            """INSERT OR IGNORE INTO toad_memes (chat_id, kind, source, file_id, uid)
               VALUES (?, ?, 'chat', ?, ?)""",
            (chat_id, kind, file_id, f"tg:{uid}"),
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def toad_meme_count(self, chat_id: int | None = None) -> int:
        """Shared memes (chat_id=None) or one chat's own collection."""
        async with self._conn.execute(
            "SELECT COUNT(*) FROM toad_memes WHERE chat_id IS ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def toad_of_day(self, chat_id: int, user_id: int, day: date) -> ToadMeme | None:
        return await self._one_toad(
            f"{_TOAD} JOIN toad_days d ON d.meme_id = m.id"
            " WHERE d.chat_id = ? AND d.user_id = ? AND d.day = ?",
            (chat_id, user_id, day.isoformat()),
        )

    async def pick_toad_meme(self, chat_id: int, day: date, *, own: bool, wednesday: bool) -> ToadMeme | None:
        """Random meme nobody in this chat got today; own: the chat's collection, else the shared one.

        Wednesday memes appear only on Wednesdays, and then they come first.
        """
        return await self._one_toad(
            f"""{_TOAD}
                WHERE m.chat_id IS ?
                  AND m.id NOT IN (SELECT meme_id FROM toad_days WHERE chat_id = ? AND day = ?)
                  AND (? OR m.source != 'itswednesdaymydudes')
                ORDER BY (m.source = 'itswednesdaymydudes') DESC, RANDOM()
                LIMIT 1""",  # noqa: S608
            (chat_id if own else None, chat_id, day.isoformat(), wednesday),
        )

    async def prune_toads(self, today: date, *, keep_shared: int, keep_days: int = 2) -> None:
        """Keeps the toad tables tiny: drops old day records and the oldest shared memes over keep_shared.

        Memes someone holds today are never dropped.
        """
        since = date.fromordinal(today.toordinal() - keep_days).isoformat()
        await self._conn.execute("DELETE FROM toad_days WHERE day < ?", (since,))
        await self._conn.execute(
            """DELETE FROM toad_memes WHERE chat_id IS NULL
                 AND id NOT IN (SELECT meme_id FROM toad_days)
                 AND id NOT IN (SELECT id FROM toad_memes WHERE chat_id IS NULL ORDER BY id DESC LIMIT ?)""",
            (keep_shared,),
        )
        await self._conn.commit()

    async def give_toad(self, chat_id: int, user_id: int, day: date, meme_id: int) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO toad_days (chat_id, user_id, day, meme_id) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, day.isoformat(), meme_id),
        )
        await self._conn.commit()

    async def set_toad_file_id(self, meme_id: int, file_id: str) -> None:
        await self._conn.execute("UPDATE toad_memes SET file_id = ? WHERE id = ?", (file_id, meme_id))
        await self._conn.commit()

    async def drop_toad_meme(self, meme_id: int) -> None:
        """A meme Telegram can't fetch any more (deleted on Reddit): forget it and who had it."""
        await self._conn.execute("DELETE FROM toad_days WHERE meme_id = ?", (meme_id,))
        await self._conn.execute("DELETE FROM toad_memes WHERE id = ?", (meme_id,))
        await self._conn.commit()

    async def _one_toad(self, query: str, args: Sequence[object]) -> ToadMeme | None:
        async with self._conn.execute(query, args) as cur:
            row = await cur.fetchone()
        return ToadMeme(*row) if row else None

    async def _one_user(self, query: str, args: Sequence[object]) -> KnownUser | None:
        async with self._conn.execute(query, args) as cur:
            row = await cur.fetchone()
        return KnownUser(*row) if row else None
