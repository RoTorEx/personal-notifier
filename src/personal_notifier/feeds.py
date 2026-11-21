"""Bounded event feeds and explicit source-owned review capabilities."""

import re
from html import unescape
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, UnixConnector


async def bounded_json(response, limit):
    import json

    parts, size = [], 0
    async for chunk in response.content.iter_chunked(16384):
        size += len(chunk)
        if size > limit:
            raise ValueError("Response exceeds size limit")
        parts.append(chunk)
    return json.loads(b"".join(parts))


def validate_presentation(value):
    if not isinstance(value, dict) or set(value) - {"html", "photo_url", "photo_urls", "copy_text"}:
        raise ValueError("Invalid presentation")
    body = value.get("html")
    if not isinstance(body, str) or not body or len(body) > 6000:
        raise ValueError("Invalid card text")
    plain = unescape(re.sub(r"<[^>]*>", "", body))
    if len(plain.encode("utf-16-le")) // 2 > 1024:
        raise ValueError("Card exceeds photo caption limit")
    photos = value.get("photo_urls", [])
    if not isinstance(photos, list) or len(photos) > 10 or any(not isinstance(url, str) for url in photos):
        raise ValueError("Invalid photo gallery")
    if len(set(photos)) != len(photos):
        raise ValueError("Duplicate gallery photos")
    for photo in photos + ([value["photo_url"]] if value.get("photo_url") is not None else []):
        if not isinstance(photo, str) or not photo or len(photo) > 3000:
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

    def session(self):
        if self.http is None:
            self.http = ClientSession(
                connector=UnixConnector(path=str(self.source.socket)), timeout=ClientTimeout(total=10)
            )
        return self.http

    async def read(self, cursor):
        async with self.session().get(
            "http://source/events",
            params={
                "after": cursor,
                "limit": 100,
                **({"topic": self.source.topic, "queue_only": "1"} if self.source.queue else {}),
            },
        ) as response:
            response.raise_for_status()
            result = await bounded_json(response, 1_000_000)
            if self.source.queue and result.get("topic", "housing") != self.source.topic:
                raise ValueError("Producer does not confirm collection topic")
            return result

    async def queue_request(
        self, mode="queue", offset=0, item=None, changes=None, actor="", sort="added", event_id=None
    ):
        if not self.source.queue:
            raise PermissionError("Queue controls are disabled for this source")
        if item is not None and self.source.topic != "housing":
            # Verify namespace before mutating, including after a producer rollback.
            await self.queue_request(actor=actor, event_id=1)
        session = self.session()
        if item is None:
            if mode not in ("queue", "favorites") or type(offset) is not int or offset < 0:
                raise ValueError("Invalid queue request")
            params = {
                "mode": mode,
                "offset": offset,
                "actor": actor,
                "sort": sort,
                "topic": self.source.topic,
            }
            if event_id is not None:
                if type(event_id) is not int or event_id <= 0:
                    raise ValueError("Invalid queue notice event")
                params["event_id"] = event_id
            request = session.get("http://source/queue", params=params)
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
            request = session.patch(
                "http://source/items/" + quote(connector, safe="") + "/" + quote(identifier, safe=""),
                params={"actor": actor, "sort": sort, "topic": self.source.topic},
                json=changes,
            )
        async with request as response:
            response.raise_for_status()
            result = await bounded_json(response, 100_000)
            if result.get("topic", "housing") != self.source.topic:
                raise ValueError("Producer does not confirm collection topic")
        if item is None:
            if (
                type(result.get("total")) is not int
                or result["total"] < 0
                or type(result.get("offset")) is not int
                or result["offset"] < 0
            ):
                raise ValueError("Invalid queue page")
            if event_id is not None and (
                type(result.get("new_total")) is not int
                or not 0 <= result["new_total"] <= result["total"]
                or result.get("event_id") != event_id
            ):
                raise ValueError("Source does not confirm notice membership")
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

    async def mark_queue_viewed(self, actor=""):
        if not self.source.queue:
            raise PermissionError("Queue controls are disabled for this source")
        async with self.session().patch(
            "http://source/queue", params={"topic": self.source.topic, "actor": actor}, json={"viewed": True}
        ) as response:
            response.raise_for_status()
            result = await bounded_json(response, 4096)
        if not isinstance(result, dict) or result.get("topic") != self.source.topic:
            raise ValueError("Producer does not confirm bulk review")
        marked = result.get("marked")
        if type(marked) is not int or marked < 0:
            raise ValueError("Producer does not confirm bulk review")
        return marked

    async def close(self):
        if self.http:
            await self.http.close()
