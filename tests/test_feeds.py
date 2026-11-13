import asyncio

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
