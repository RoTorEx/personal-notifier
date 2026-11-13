"""Rich outbound cards keep queue receipts and never need incoming updates."""

import json
import sqlite3

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendMessage, SendPhoto
from test_bot import TelegramFake

from personal_notifier.config import FeedSource, Settings
from personal_notifier.feeds import validate_presentation
from personal_notifier.notifier import Notifier


def card(phone=True, photo=True):
    return {
        "html": "<b>2 800 PLN / month</b>\n\n📍 Saska Kępa\n\n<code>+48501234567</code>",
        "photo_url": "https://ireland.apollo.olxcdn.com/photo" if photo else None,
        "copy_text": "+48501234567" if phone else None,
    }


@pytest.mark.parametrize(
    "value",
    [
        {"html": "🏠" * 513},
        {"html": "Fine", "photo_url": "file:///etc/passwd"},
        {"html": "Fine", "photo_url": "https://user:secret@example.com/photo"},
        {"html": "Fine", "copy_text": "x" * 257},
        {"html": "Fine", "callback_data": "run:anything"},
    ],
)
def test_invalid_presentation_is_rejected(value):
    with pytest.raises(ValueError):
        validate_presentation(value)


@pytest.fixture
async def app(tmp_path):
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
    notifier = Notifier(settings, bot=bot)
    yield notifier, bot.session, source
    notifier.store.close()
    await bot.session.close()


async def queue(app, presentation):
    notifier, transport, source = app

    class Feed:
        async def read(self, cursor):
            return {
                "version": 1,
                "next_cursor": 1,
                "events": []
                if cursor
                else [
                    {
                        "id": 1,
                        "type": "housing.listing.updated",
                        "title": "Studio",
                        "text": "Verify costs",
                        "url": "https://www.olx.pl/d/oferta/test",
                        "priority": 2,
                        "presentation": presentation,
                    }
                ],
            }

    notifier.feeds[source.name] = Feed()
    await notifier.collect_feed(source)
    assert (
        json.loads(notifier.store.one("SELECT presentation FROM feed_notices")["presentation"])
        == presentation
    )


async def test_photo_caption_copy_button_and_known_receipt_do_not_repeat(app):
    notifier, transport, _ = app
    await queue(app, card())
    await notifier.deliver()
    await notifier.deliver()
    messages = [m for m in transport.calls if isinstance(m, (SendPhoto, SendMessage))]
    assert len(messages) == 1 and isinstance(messages[0], SendPhoto)
    message = messages[0]
    assert message.caption == card()["html"] and message.parse_mode == "HTML"
    button = message.reply_markup.inline_keyboard[0][0]
    assert button.copy_text.text == "+48501234567" and button.callback_data is None
    assert notifier.store.one("SELECT telegram_id FROM feed_notices")["telegram_id"] == 101


async def test_missing_photo_and_phone_delivers_readable_text_without_button(app):
    notifier, transport, _ = app
    await queue(app, card(phone=False, photo=False))
    await notifier.deliver()
    sent = next(m for m in transport.calls if isinstance(m, SendMessage))
    assert sent.reply_markup is None and sent.parse_mode == "HTML"


@pytest.mark.parametrize("ambiguous", [False, True])
async def test_only_explicit_photo_rejection_falls_back_to_text(app, ambiguous):
    notifier, transport, _ = app
    await queue(app, card())
    original = transport.make_request

    async def fail_photo(bot, method, timeout=None):
        if isinstance(method, SendPhoto):
            transport.calls.append(method)
            error = TelegramNetworkError if ambiguous else TelegramBadRequest
            raise error(method=method, message="Image unavailable")
        return await original(bot, method, timeout)

    transport.make_request = fail_photo
    if ambiguous:
        with pytest.raises(TelegramNetworkError):
            await notifier.deliver()
        assert notifier.store.one("SELECT telegram_id FROM feed_notices")["telegram_id"] is None
        assert not any(isinstance(m, SendMessage) for m in transport.calls)
    else:
        await notifier.deliver()
        assert any(isinstance(m, SendMessage) for m in transport.calls)
        assert notifier.store.one("SELECT telegram_id FROM feed_notices")["telegram_id"] is not None


async def test_old_queue_schema_preserves_receipts_and_pending_cards(tmp_path):
    db = sqlite3.connect(tmp_path / "bot.db")
    db.execute(
        "CREATE TABLE feed_notices(source TEXT,event_id INTEGER,body TEXT,url TEXT,"
        "priority INTEGER,created REAL,telegram_id INTEGER,PRIMARY KEY(source,event_id))"
    )
    db.execute("INSERT INTO feed_notices VALUES('housing',7,'Already delivered','',2,1,123)")
    db.execute("INSERT INTO feed_notices VALUES('housing',8,'Still pending','',2,2,NULL)")
    db.commit()
    db.close()
    settings = Settings(tmp_path, tmp_path / "run", tmp_path / "token", allowed_user_id=42)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=TelegramFake())
    notifier = Notifier(settings, bot=bot)
    await notifier.deliver()
    rows = notifier.store.rows("SELECT * FROM feed_notices ORDER BY event_id")
    assert rows[0]["telegram_id"] == 123 and rows[0]["presentation"] is None
    assert rows[1]["telegram_id"] == 101
    notifier.store.close()
    await bot.session.close()
