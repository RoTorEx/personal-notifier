"""Bounded event feeds and explicit source-owned review capabilities."""

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

    async def queue_request(self, mode="queue", offset=0, item=None, changes=None):
        if not self.source.queue:
            raise PermissionError("Queue controls are disabled for this source")
        if self.http is None:
            self.http = ClientSession(
                connector=UnixConnector(path=str(self.source.socket)), timeout=ClientTimeout(total=10)
            )
        if item is None:
            if mode not in ("queue", "favorites") or type(offset) is not int or offset < 0:
                raise ValueError("Invalid queue request")
            request = self.http.get("http://source/queue", params={"mode": mode, "offset": offset})
        else:
            if (
                not isinstance(changes, dict)
                or not changes
                or set(changes) - {"viewed", "favorite"}
                or any(type(v) is not bool for v in changes.values())
            ):
                raise ValueError("Invalid review state")
            from urllib.parse import quote

            connector, identifier = item
            request = self.http.patch(
                "http://source/items/" + quote(connector, safe="") + "/" + quote(identifier, safe=""),
                json=changes,
            )
        async with request as response:
            response.raise_for_status()
            raw = await response.content.read(100_001)
            if len(raw) > 100_000:
                raise ValueError("Queue response exceeds limit")
            import json

            result = json.loads(raw)
        if item is None:
            if (
                type(result.get("total")) is not int
                or result["total"] < 0
                or type(result.get("offset")) is not int
                or result["offset"] < 0
            ):
                raise ValueError("Invalid queue page")
            card = result.get("item")
            if card is not None:
                if any(not isinstance(card.get(k), str) for k in ("connector", "id", "url")):
                    raise ValueError("Invalid queue item")
                if any(type(card.get(k)) is not bool for k in ("favorite", "viewed")):
                    raise ValueError("Invalid review flags")
                parsed = urlsplit(card["url"])
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Invalid listing link")
                validate_presentation(card["presentation"])
        return result

    async def close(self):
        if self.http:
            await self.http.close()
