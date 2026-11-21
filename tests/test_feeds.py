import asyncio
import tempfile
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from test_bot import TelegramFake

from personal_notifier.config import FeedSource, Settings
from personal_notifier.feeds import validate_page
from personal_notifier.notifier import Notifier


def page(identifier=1):
    return {
        "version": 1,
        "events": [
            {
                "id": identifier,
                "type": "housing.listing.discovered",
                "title": "New housing",
                "text": "Verify costs",
                "url": "https://www.otodom.pl/pl/oferta/test",
                "priority": 2,
            }
        ],
        "next_cursor": identifier,
    }


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(next_cursor=100),
        lambda p: p["events"][0].update(id=0),
        lambda p: p["events"][0].update(url="javascript:alert(1)"),
        lambda p: p["events"][0].update(priority=3),
    ],
)
def test_invalid_event_cannot_advance_cursor(change):
    value = page()
    change(value)
    with pytest.raises(ValueError):
        validate_page(value, 0)


async def test_source_cursor_queue_and_restart(tmp_path):
    source = FeedSource("housing", tmp_path / "api.sock")
    settings = Settings(
        tmp_path,
        tmp_path / "run",
        tmp_path / "token",
        allowed_user_id=42,
        core_enabled=False,
        sources=(source,),
    )
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=TelegramFake())
    app = Notifier(settings, bot=bot)

    class Feed:
        async def read(self, cursor):
            return page() if cursor == 0 else {"version": 1, "events": [], "next_cursor": cursor}

        async def close(self):
            pass

    app.feeds["housing"] = Feed()
    await app.collect_feed(source)
    await app.collect_feed(source)
    assert app.store.get("feed_cursor:housing") == "1"
    assert len(app.store.rows("SELECT * FROM feed_notices")) == 1
    await app.deliver()
    messages = [c for c in bot.session.calls if isinstance(c, SendMessage)]
    assert len(messages) == 1 and messages[0].reply_markup is None
    assert messages[0].text.endswith("https://www.otodom.pl/pl/oferta/test")
    app.store.close()
    restored = Notifier(settings, bot=bot)
    await restored.deliver()
    assert len([c for c in bot.session.calls if isinstance(c, SendMessage)]) == 1
    restored.store.close()
    await bot.session.close()


async def test_delivery_continues_when_core_is_unavailable(tmp_path):
    settings = Settings(tmp_path, tmp_path / "run", tmp_path / "token", allowed_user_id=42)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=TelegramFake())
    app = Notifier(settings, bot=bot)
    with app.store.db:
        app.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created,telegram_id) VALUES(?,?,?,?,?,?,NULL)",
            ("housing", 1, "Candidate", "https://www.olx.pl/d/oferta/test", 2, 1),
        )

    async def broken():
        raise ConnectionError("Core down")

    app.snapshot = broken
    core = asyncio.create_task(app.core_loop())
    delivery = asyncio.create_task(app.notifications())
    try:
        for _ in range(30):
            await asyncio.sleep(0.01)
            if app.store.one("SELECT telegram_id FROM feed_notices")["telegram_id"]:
                break
        assert app.store.one("SELECT telegram_id FROM feed_notices")["telegram_id"] is not None
    finally:
        app.stop.set()
        await asyncio.gather(core, delivery)
        app.store.close()
        await bot.session.close()


@pytest.mark.parametrize(
    "photos",
    [
        ["http://example.org/a"],
        ["https://u:p@example.org/a"],
        ["https://example.org/a"] * 2,
        ["https://example.org/" + str(i) for i in range(11)],
        [None],
        "https://example.org/a",
    ],
)
def test_invalid_gallery_cannot_advance_cursor(photos):
    value = page()
    value["events"][0]["presentation"] = {
        "html": "A listing",
        "photo_url": None,
        "photo_urls": photos,
        "copy_text": None,
    }
    with pytest.raises(ValueError):
        validate_page(value, 0)


@pytest.mark.parametrize("topic", ["market.digital_pianos", "market.keyboards"])
async def test_real_feed_client_captures_delivers_and_browses_gallery_then_keeps_receipt(tmp_path, topic):
    from aiogram.methods import SendRichMessage
    from aiohttp import web
    from test_review_ui import action, callback

    socket_dir = tempfile.TemporaryDirectory(prefix="pn-", dir="/tmp")
    socket = Path(socket_dir.name) / "source.sock"
    source = FeedSource("pianos", socket, queue=True, topic=topic)
    settings = Settings(
        tmp_path / "state",
        tmp_path / "run",
        tmp_path / "token",
        allowed_user_id=42,
        core_enabled=False,
        sources=(source,),
    )
    photos = ["https://ireland.apollo.olxcdn.com/one", "https://ireland.apollo.olxcdn.com/two"]
    card = {
        "connector": "olx",
        "id": "123",
        "url": "https://www.olx.pl/d/oferta/piano",
        "viewed": False,
        "favorite": False,
        "presentation": {
            "html": "<b>Yamaha P-45</b>",
            "photo_url": photos[0],
            "photo_urls": photos,
            "copy_text": None,
        },
    }
    discovered = {
        "id": 1,
        "type": topic + ".listing.discovered",
        "title": "Piano",
        "text": "Piano found",
        "url": card["url"],
        "priority": 0,
        "presentation": card["presentation"],
    }
    summary = {
        "id": 2,
        "type": topic + ".queue.summary",
        "title": "🎹 Digital pianos alert",
        "text": "1 new · 1 in queue",
        "url": "",
        "priority": 2,
    }
    calls = []
    bulk_calls = []

    async def events(request):
        # An older source ignores the optional filter; gallery validation must
        # still accept its mixed event page before the cursor can be committed.
        assert request.query["queue_only"] == "1"
        after = int(request.query["after"])
        rows = [event for event in (discovered, summary) if event["id"] > after]
        return web.json_response(
            {
                "version": 1,
                "topic": source.topic,
                "events": rows,
                "next_cursor": rows[-1]["id"] if rows else after,
            }
        )

    async def queue(request):
        calls.append(dict(request.query))
        result = {
            "topic": source.topic,
            "total": int(not card["viewed"]),
            "offset": 0,
            "item": None if card["viewed"] else card,
            "last_refresh": "2026-11-18T12:00:00Z",
        }
        if "event_id" in request.query:
            result.update(event_id=int(request.query["event_id"]), new_total=1)
        return web.json_response(result)

    async def mark_all(request):
        assert dict(request.query) == {"topic": topic, "actor": ""}
        assert await request.json() == {"viewed": True}
        bulk_calls.append(topic)
        card["viewed"] = True
        return web.json_response({"topic": topic, "marked": 1})

    server = web.Application()
    server.router.add_get("/events", events)
    server.router.add_get("/queue", queue)
    server.router.add_patch("/queue", mark_all)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.UnixSite(runner, str(socket)).start()
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=TelegramFake())
    app = Notifier(settings, bot=bot)
    try:
        await app.collect_feed(source)
        assert app.store.get("feed_cursor:pianos") == "2"
        assert len(app.store.rows("SELECT * FROM feed_notices")) == 1
        await app.deliver()
        assert len([call for call in bot.session.calls if isinstance(call, SendMessage)]) == 1
        assert app.store.one("SELECT telegram_id FROM housing_receipts")["telegram_id"]
        await app.review.market()
        market_message = bot.session.calls[-1]
        buttons = [b.text for row in market_message.reply_markup.inline_keyboard for b in row]
        assert ("⌨️ Keyboards" if topic == "market.keyboards" else "🎹 Digital pianos") in buttons
        await app.review.housing("pianos")
        section_message = bot.session.calls[-1]
        section_buttons = [b.text for row in section_message.reply_markup.inline_keyboard for b in row]
        assert "📋 Queue" in section_buttons and "⭐ Favorites" in section_buttons
        await app.review.browse("pianos", "queue")
        assert len([call for call in bot.session.calls if isinstance(call, SendRichMessage)]) == 1
        assert any(query.get("event_id") == "2" for query in calls)
        await app.feeds["pianos"].close()
        app.store.close()
        app = Notifier(settings, bot=bot)
        await app.deliver()
        assert len([call for call in bot.session.calls if isinstance(call, SendMessage)]) == 3
        screen = await app.review.browse("pianos", "queue")
        mark = callback(screen, action(screen, "Mark all viewed"))
        await app.handle(mark)
        assert card["viewed"]
        assert "Marked as viewed · 1" in bot.session.messages[screen.message_id].text
        card["viewed"] = False  # A new unviewed card appears after the bulk action.
        await app.handle(mark)
        assert bulk_calls == [topic] and not card["viewed"]
    finally:
        await app.review.close()
        await app.feeds["pianos"].close()
        app.store.close()
        await bot.session.close()
        await runner.cleanup()
        socket_dir.cleanup()
