from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from bot.db import Database, Pin
from bot.pinterest import REFRESH_KEY, SYNC_EVERY, PinterestBoard, pin_image
from tests.helpers import FakeClock


def image(url: str, pin_id: str = "1", kind: str = "image") -> dict[str, Any]:
    return {
        "id": pin_id,
        "media": {
            "media_type": kind,
            "images": {"600x": {"width": 600, "url": url + "?s"}, "1200x": {"width": 1200, "url": url}},
        },
    }


class FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if "error" in self.data:
            raise aiohttp.ClientError(self.data["error"])

    async def json(self) -> dict[str, Any]:
        return self.data


class FakeSession:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(self.responses.pop(0))

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(self.responses.pop(0))


def board(session: FakeSession, clock: FakeClock) -> PinterestBoard:
    return PinterestBoard(
        app_id="app",
        app_secret=SecretStr("secret"),
        refresh_token=SecretStr("refresh-from-env"),
        board_id="123",
        session=cast(Any, lambda: session),
        clock=clock,
    )


def test_pin_image_takes_large_pictures_only() -> None:
    assert pin_image(image("https://i.pinimg.com/a.jpg")) == Pin("1", "https://i.pinimg.com/a.jpg", "photo")
    assert pin_image(image("https://i.pinimg.com/a.GIF", "2")) == Pin(
        "2", "https://i.pinimg.com/a.GIF", "animation"
    )
    assert pin_image(image("https://i.pinimg.com/v.jpg", kind="video")) is None
    assert pin_image(image("http://i.pinimg.com/a.jpg")) is None
    assert pin_image({}) is None


async def test_sync_pages_through_board_and_keeps_renewed_token(db: Database) -> None:
    session = FakeSession(
        [
            {"access_token": "AT", "expires_in": 2592000, "refresh_token": "renewed"},
            {"items": [image("https://i.pinimg.com/1.jpg", "1")], "bookmark": "next"},
            {
                "items": [image("https://i.pinimg.com/2.jpg", "2"), image("https://x/v.mp4", "3", "video")],
                "bookmark": None,
            },
        ]
    )
    clock = FakeClock()
    pins = await board(session, clock).pins(db)
    assert [p.id for p in pins] == ["1", "2"]
    post, first, second = session.calls
    assert post[2]["data"]["refresh_token"] == "refresh-from-env"
    assert first[1].endswith("/boards/123/pins") and first[2]["headers"]["Authorization"] == "Bearer AT"
    assert second[2]["params"]["bookmark"] == "next"
    assert await db.get_value(REFRESH_KEY) == "renewed"


async def test_pins_are_cached_and_survive_api_errors(db: Database) -> None:
    session = FakeSession(
        [
            {"access_token": "AT", "expires_in": 2592000},
            {"items": [image("https://i.pinimg.com/1.jpg")], "bookmark": None},
        ]
    )
    clock = FakeClock()
    pinterest = board(session, clock)
    assert len(await pinterest.pins(db)) == 1
    assert len(await pinterest.pins(db)) == 1  # cached: no new calls
    assert len(session.calls) == 2
    clock.t += SYNC_EVERY + 1
    session.responses.append({"error": "down"})
    assert len(await pinterest.pins(db)) == 1  # last good list stays


async def test_db_pins_and_state(db: Database) -> None:
    await db.replace_pins([Pin("b", "https://x/b.jpg", "photo"), Pin("a", "https://x/a.gif", "animation")])
    assert [p.id for p in await db.pins()] == ["b", "a"]
    await db.replace_pins([])
    assert await db.pins() == []
    assert await db.get_value("k") is None
    await db.set_value("k", "1")
    await db.set_value("k", "2")
    assert await db.get_value("k") == "2"
