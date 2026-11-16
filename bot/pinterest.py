"""Pictures for /жаба from our Pinterest board (API v5).

We only keep links, telegram downloads the pictures by itself.
The access token dies after ~30 days, we get a new one with the refresh token.
"""

import asyncio
import base64
import logging
import time
from collections.abc import Callable
from typing import Any, Self

import aiohttp
from pydantic import SecretStr

from bot.config import Settings
from bot.db import Database, Pin

log = logging.getLogger(__name__)

API_URL = "https://api.pinterest.com/v5"
TOKEN_URL = f"{API_URL}/oauth/token"
SYNC_EVERY = 12 * 3600  # pick up pins added to the board twice a day
RETRY_AFTER = 600  # after a failed sync, don't hammer the API
PAGE_SIZE = 100
MAX_PAGES = 20  # 2000 pins is more than enough for a meme board
TOKEN_MARGIN = 300  # renew the token a bit before it expires
REFRESH_KEY = "pinterest_refresh_token"  # a renewed refresh token outlives the one in .env
TIMEOUT = aiohttp.ClientTimeout(total=20)

type SessionFactory = Callable[[], aiohttp.ClientSession]


def pin_image(item: dict[str, Any]) -> Pin | None:
    # videos and carousels are skipped
    media = item.get("media") or {}
    if media.get("media_type") != "image":
        return None
    images: dict[str, dict[str, Any]] = media.get("images") or {}
    best = images.get("1200x") or max(images.values(), key=lambda i: i.get("width") or 0, default={})
    url = str(best.get("url") or "")
    if not url.startswith("https://"):
        return None
    kind = "animation" if url.lower().split("?")[0].endswith(".gif") else "photo"
    return Pin(str(item.get("id") or url), url, kind)


def _new_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=TIMEOUT)


class PinterestBoard:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: SecretStr,
        refresh_token: SecretStr,
        board_id: str,
        session: SessionFactory = _new_session,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._refresh_token = refresh_token
        self._board_id = board_id
        self._session = session
        self._clock = clock
        self._lock = asyncio.Lock()
        self._synced = float("-inf")
        self._token: str | None = None
        self._token_expires = float("-inf")

    @classmethod
    def from_settings(cls, settings: Settings) -> Self | None:
        if not settings.pinterest_ready:
            return None
        return cls(
            app_id=settings.pinterest_app_id,
            app_secret=settings.pinterest_app_secret,
            refresh_token=settings.pinterest_refresh_token,
            board_id=settings.pinterest_board_id,
        )

    async def pins(self, db: Database) -> list[Pin]:
        # if pinterest is down we keep using the last list we got
        async with self._lock:
            if self._clock() - self._synced > SYNC_EVERY:
                await self._sync(db)
        return await db.pins()

    async def _sync(self, db: Database) -> None:
        try:
            pins = await self._fetch_pins(db)
        except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as exc:
            log.warning("pinterest sync failed: %s", exc)
            self._synced = self._clock() - SYNC_EVERY + RETRY_AFTER
            return
        await db.replace_pins(pins)
        self._synced = self._clock()
        log.info("pinterest: %s pins on the board", len(pins))

    async def _fetch_pins(self, db: Database) -> list[Pin]:
        pins: list[Pin] = []
        async with self._session() as session:
            headers = {"Authorization": f"Bearer {await self._access_token(session, db)}"}
            bookmark: str | None = None
            for _ in range(MAX_PAGES):
                params: dict[str, str | int] = {"page_size": PAGE_SIZE}
                if bookmark:
                    params["bookmark"] = bookmark
                url = f"{API_URL}/boards/{self._board_id}/pins"
                async with session.get(url, params=params, headers=headers) as response:
                    response.raise_for_status()
                    page = await response.json()
                pins += [pin for item in page.get("items") or () if (pin := pin_image(item))]
                bookmark = page.get("bookmark")
                if not bookmark:
                    break
        return pins

    async def _access_token(self, session: aiohttp.ClientSession, db: Database) -> str:
        if self._token and self._clock() < self._token_expires:
            return self._token
        refresh = await db.get_value(REFRESH_KEY) or self._refresh_token.get_secret_value()
        pair = f"{self._app_id}:{self._app_secret.get_secret_value()}".encode()
        headers = {"Authorization": "Basic " + base64.b64encode(pair).decode()}
        data = {"grant_type": "refresh_token", "refresh_token": refresh}
        async with session.post(TOKEN_URL, data=data, headers=headers) as response:
            response.raise_for_status()
            answer = await response.json()
        self._token = str(answer["access_token"])
        self._token_expires = self._clock() + int(answer.get("expires_in", 3600)) - TOKEN_MARGIN
        if renewed := answer.get("refresh_token"):
            await db.set_value(REFRESH_KEY, str(renewed))
        return self._token
