"""Read-only, bounded pull contract for independent personal event sources."""

import re
from html import unescape
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, UnixConnector


def validate_presentation(value):
    if not isinstance(value, dict) or set(value) - {"html", "photo_url", "copy_text"}:
        raise ValueError("Invalid presentation")
    body = value.get("html")
    if not isinstance(body, str) or not body or len(body) > 6000:
        raise ValueError("Invalid card text")
    plain = unescape(re.sub(r"<[^>]*>", "", body))
    if len(plain.encode("utf-16-le")) // 2 > 1024:
        raise ValueError("Card exceeds photo caption limit")
    photo = value.get("photo_url")
    if photo is not None:
        if not isinstance(photo, str) or len(photo) > 3000:
            raise ValueError("Invalid photo URL")
        parsed = urlsplit(photo)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid photo URL")
    copy = value.get("copy_text")
    if copy is not None and (not isinstance(copy, str) or not 1 <= len(copy) <= 256):
        raise ValueError("Invalid copy text")
    return value


def validate_page(page, cursor):
    if not isinstance(page, dict) or page.get("version") != 1 or not isinstance(page.get("events"), list):
        raise ValueError("Unsupported event page")
    events = page["events"]
    if len(events) > 100:
        raise ValueError("Event page exceeds limit")
    previous = cursor
    for event in events:
        if type(event.get("id")) is not int or event["id"] <= previous:
            raise ValueError("Event IDs must be strictly increasing")
        previous = event["id"]
        if "presentation" in event:
            validate_presentation(event["presentation"])
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", event.get("type", "")):
            raise ValueError("Invalid event type")
        for key, limit in (("title", 200), ("text", 3000), ("url", 500)):
            if not isinstance(event.get(key), str) or len(event[key]) > limit:
                raise ValueError("Invalid event text")
        parsed = urlsplit(event["url"])
        if event["url"] and (
            parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        ):
            raise ValueError("Invalid event link")
        if type(event.get("priority")) is not int or event["priority"] not in (0, 1, 2):
            raise ValueError("Invalid event priority")
    if type(page.get("next_cursor")) is not int or page["next_cursor"] != previous:
        raise ValueError("Cursor must match the last retained event")
    return page


class FeedClient:
    def __init__(self, source):
        self.source = source
        self.http = None

    async def read(self, cursor):
        if self.http is None:
            self.http = ClientSession(
                connector=UnixConnector(path=str(self.source.socket)), timeout=ClientTimeout(total=10)
            )
        async with self.http.get("http://source/events", params={"after": cursor, "limit": 100}) as response:
            response.raise_for_status()
            raw = await response.content.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("Event response exceeds size limit")
            import json

            return json.loads(raw)

    async def close(self):
        if self.http:
            await self.http.close()
