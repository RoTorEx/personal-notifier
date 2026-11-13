"""Exercise deck, carousel, source writes and owner checks through real handlers."""

from copy import deepcopy

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageMedia, SendMessage, SendPhoto
from aiogram.types import Update
from test_bot import TelegramFake, update

from personal_notifier.config import FeedSource, Settings
from personal_notifier.notifier import Notifier


class QueueFeed:
    def __init__(self):
        self.calls = []
        self.items = [
            {
                "connector": "olx",
                "id": str(i),
                "viewed": False,
                "favorite": False,
                "url": f"https://www.olx.pl/d/oferta/test-{i}",
                "presentation": {
                    "html": f"Published: 13 Nov 2026\nSeller: Private\n\nFlat {i}",
                    "photo_url": "https://ireland.apollo.olxcdn.com/photo",
                    "copy_text": "+48501234567",
                },
            }
            for i in range(3)
        ]

    async def queue_request(self, mode="queue", offset=0, item=None, changes=None):
        self.calls.append((mode, offset, item, changes))
        if item:
            next(i for i in self.items if (i["connector"], i["id"]) == item).update(changes)
            return {"ok": True}
        visible = (
            [i for i in self.items if i["favorite"]]
            if mode == "favorites"
            else [i for i in self.items if not i["viewed"]]
        )
        offset = min(offset, max(0, len(visible) - 1))
        return {
            "total": len(visible),
            "offset": offset,
            "item": deepcopy(visible[offset]) if visible else None,
        }

    async def close(self):
        pass


@pytest.fixture
async def app(tmp_path):
    source = FeedSource("housing", tmp_path / "api.sock", queue=True)
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
    app.feeds["housing"] = QueueFeed()
    yield app
    app.store.close()
    await bot.session.close()


def callback(message, data, owner=42, chat=None):
    value = message.model_dump(mode="json")
    if chat is not None:
        value["chat"] = {"id": chat, "type": "group", "title": "Group"}
    return Update.model_validate(
        {
            "update_id": 99,
            "callback_query": {
                "id": data,
                "from": {"id": owner, "is_bot": False, "first_name": "Owner"},
                "chat_instance": "private",
                "data": data,
                "message": value,
            },
        }
    )


def action(message, text):
    return next(
        b.callback_data for row in message.reply_markup.inline_keyboard for b in row if text in b.text
    )


async def test_deck_vibecoding_alert_housing_carousel_and_separate_back(app):
    await app.handle(Update.model_validate(update(text="/menu")))
    deck = list(app.bot.session.messages.values())[-1]
    assert [[b.text for b in row] for row in deck.reply_markup.inline_keyboard] == [
        ["Vibecoding"],
        ["Housing"],
    ]
    before = len(app.bot.session.calls)
    await app.handle(callback(deck, "vibecoding"))
    calls = app.bot.session.calls[before:]
    assert len(calls) == 1 and isinstance(calls[0], AnswerCallbackQuery)
    assert calls[0].text == "Under construction" and calls[0].show_alert is True
    assert not app.feeds["housing"].calls
    await app.handle(callback(deck, action(deck, "Housing")))
    card = list(app.bot.session.messages.values())[-1]
    rows = card.reply_markup.inline_keyboard
    assert [b.text for b in rows[0]] == ["✓ Viewed", "☆ Favorite"]
    assert [b.text for b in rows[-1]] == ["← Back", "🏠 Deck"]
    assert rows[-2][-1].text == "→"
    assert rows[2][0].url.startswith("https://www.olx.pl/")
    assert rows[2][1].copy_text.text == "+48501234567"
    assert card.message_id == deck.message_id
    original_id = card.message_id
    await app.handle(callback(card, action(card, "→")))
    changed = app.bot.session.messages[original_id]
    assert "Flat 1" in changed.caption
    assert any(isinstance(m, EditMessageMedia) for m in app.bot.session.calls)
    await app.handle(callback(changed, action(changed, "Back")))
    assert "Home deck" in (
        list(app.bot.session.messages.values())[-1].caption
        or list(app.bot.session.messages.values())[-1].text
    )
    assert list(app.bot.session.messages.values())[-1].message_id == original_id


async def test_viewed_favorite_empty_favorites_back_and_stale_controls(app):
    await app.review.browse("housing", "queue")
    card = list(app.bot.session.messages.values())[-1]
    old = callback(card, action(card, "Favorite"))
    await app.handle(old)
    assert app.feeds["housing"].items[0]["favorite"] is True
    writes = len([c for c in app.feeds["housing"].calls if c[2]])
    await app.handle(old)
    assert len([c for c in app.feeds["housing"].calls if c[2]]) == writes
    card = app.bot.session.messages[card.message_id]
    await app.handle(callback(card, action(card, "Viewed")))
    assert app.feeds["housing"].items[0]["viewed"] is True
    card = app.bot.session.messages[card.message_id]
    assert "Flat 1" in card.caption
    await app.handle(callback(card, action(card, "Favorites")))
    card = app.bot.session.messages[card.message_id]
    assert "Flat 0" in card.caption
    assert any("Unview" in b.text for row in card.reply_markup.inline_keyboard for b in row)
    await app.handle(callback(card, action(card, "Back")))
    card = app.bot.session.messages[card.message_id]
    assert "Flat 1" in card.caption
    for i in app.feeds["housing"].items:
        i["viewed"] = True
    await app.review.browse("housing", "queue", message=card)
    empty = list(app.bot.session.messages.values())[-1]
    assert "caught up" in (empty.caption or empty.text)
    assert [b.text for b in empty.reply_markup.inline_keyboard[-1]] == ["← Back", "🏠 Deck"]


@pytest.mark.parametrize("owner,chat", [(99, None), (42, -42), (99, -42)])
async def test_other_users_and_groups_cannot_read_or_change_anything(app, owner, chat):
    await app.review.home()
    deck = list(app.bot.session.messages.values())[-1]
    before = len(app.bot.session.calls)
    for data in ("vibecoding", "home", "browse:housing:queue", "back:housing:home", "view:fake:viewed"):
        await app.handle(callback(deck, data, owner=owner, chat=chat))
    value = update(owner=owner, text="/housing")
    if chat:
        value["message"]["chat"] = {"id": chat, "type": "group", "title": "Group"}
    await app.handle(Update.model_validate(value))
    assert len(app.bot.session.calls) == before
    assert not app.feeds["housing"].calls


async def test_summary_only_delivery_skips_individual_listing_events(app):
    source = app.settings.sources[0]

    async def read(cursor):
        events = (
            []
            if cursor
            else [
                {
                    "id": 1,
                    "type": "housing.listing.discovered",
                    "title": "Flat",
                    "text": "Individual",
                    "url": "",
                    "priority": 2,
                },
                {
                    "id": 2,
                    "type": "housing.queue.summary",
                    "title": "2 new listings",
                    "text": "2 new listings found.",
                    "url": "",
                    "priority": 2,
                },
            ]
        )
        return {"version": 1, "events": events, "next_cursor": 2}

    app.feeds["housing"].read = read
    await app.collect_feed(source)
    await app.deliver()
    await app.collect_feed(source)
    await app.deliver()
    sent = [m for m in app.bot.session.calls if isinstance(m, (SendMessage, SendPhoto))]
    assert len(sent) == 1 and isinstance(sent[0], SendMessage)
    assert sent[0].reply_markup.inline_keyboard[0][0].text == "View queue"
    assert app.store.get("feed_cursor:housing") == "2"


async def test_digest_opens_in_place_and_all_screens_keep_one_message(app):
    from aiogram.methods import DeleteMessage

    sent = await app.review.summary("housing", "Housing alert\n2 new")
    original_id = sent.message_id
    await app.handle(callback(sent, action(sent, "View queue")))
    card = app.bot.session.messages[original_id]
    assert card.caption and card.reply_markup
    await app.handle(callback(card, action(card, "→")))
    card = app.bot.session.messages[original_id]
    assert "Flat 1" in card.caption
    await app.handle(callback(card, action(card, "Favorites")))
    empty = app.bot.session.messages[original_id]
    assert "No favorites" in empty.caption
    await app.handle(callback(empty, action(empty, "Back")))
    card = app.bot.session.messages[original_id]
    await app.handle(callback(card, action(card, "Deck")))
    deck = app.bot.session.messages[original_id]
    assert "Home deck" in deck.caption
    await app.handle(callback(deck, action(deck, "Housing")))
    assert app.bot.session.messages[original_id].reply_markup
    assert len(app.bot.session.messages) == 1
    assert len([m for m in app.bot.session.calls if isinstance(m, (SendMessage, SendPhoto))]) == 1
    assert not any(isinstance(m, DeleteMessage) for m in app.bot.session.calls)


async def test_no_photo_and_rejected_photo_keep_existing_card_id(app):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import DeleteMessage

    first = await app.review.browse("housing", "queue")
    app.feeds["housing"].items[1]["presentation"]["photo_url"] = None
    second = await app.review.browse("housing", "queue", 1, message=first)
    assert second.message_id == first.message_id and "Flat 1" in second.caption
    original = app.bot.session.make_request

    async def reject_url(bot, method, timeout=None):
        if isinstance(method, EditMessageMedia) and isinstance(method.media.media, str):
            app.bot.session.calls.append(method)
            raise TelegramBadRequest(method=method, message="Wrong HTTP URL")
        return await original(bot, method, timeout)

    app.bot.session.make_request = reject_url
    third = await app.review.browse("housing", "queue", 2, message=second)
    assert third.message_id == first.message_id and "Flat 2" in third.caption
    assert not any(isinstance(m, DeleteMessage) for m in app.bot.session.calls)
    assert len([m for m in app.bot.session.calls if isinstance(m, (SendMessage, SendPhoto))]) == 1


async def test_successful_screen_without_keyboard_is_repaired(app):
    from aiogram.methods import EditMessageReplyMarkup

    original = app.bot.session.make_request

    async def lose_keyboard(bot, method, timeout=None):
        if isinstance(method, EditMessageReplyMarkup):
            app.bot.session.calls.append(method)
            result = app.bot.session.messages[method.message_id].model_copy(
                update={"reply_markup": method.reply_markup}
            )
            app.bot.session.messages[method.message_id] = result
            return result
        result = await original(bot, method, timeout)
        if isinstance(method, SendPhoto):
            result = result.model_copy(update={"reply_markup": None})
            app.bot.session.messages[result.message_id] = result
        return result

    app.bot.session.make_request = lose_keyboard
    sent = await app.review.browse("housing", "queue")
    assert sent.reply_markup and sent.reply_markup.inline_keyboard
    assert any(isinstance(m, EditMessageReplyMarkup) for m in app.bot.session.calls)
