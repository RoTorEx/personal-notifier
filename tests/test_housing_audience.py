"""Two private recipients, pinned enrollment, separate UI tokens and receipts."""

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import Chat, Message, Update
from test_bot import TelegramFake, update
from test_review_ui import QueueFeed, action, callback

from personal_notifier.config import FeedSource, Settings
from personal_notifier.notifier import Notifier


@pytest.fixture
async def pair(tmp_path):
    settings = Settings(
        tmp_path,
        tmp_path / "run",
        tmp_path / "token",
        allowed_user_id=42,
        core_enabled=False,
        housing_usernames=("rental_partner",),
        sources=(FeedSource("housing", tmp_path / "api.sock", queue=True),),
    )
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=TelegramFake())
    app = Notifier(settings, bot=bot)
    app.feeds["housing"] = QueueFeed()
    original = bot.session.make_request

    async def routed(bot, method, timeout=None):
        result = await original(bot, method, timeout)
        if isinstance(result, Message) and getattr(method, "chat_id", None):
            result = result.model_copy(update={"chat": Chat(id=method.chat_id, type="private")})
            bot.session.messages[result.message_id] = result
        return result

    bot.session.make_request = routed
    yield app
    app.store.close()
    await bot.session.close()


def start(user=99, username="rental_partner", chat=None):
    value = update(owner=user, text="/start")
    value["message"]["from"]["username"] = username
    if chat:
        value["message"]["chat"] = {"id": chat, "type": "group", "title": "Group"}
    return Update.model_validate(value)


async def enroll_housing(pair):
    await pair.handle(start())
    await pair.handle(Update.model_validate(update(owner=99, text="/menu")))


async def test_private_start_registers_by_numeric_id_and_only_greets(pair):
    await pair.handle(start(chat=-99))
    assert not pair.bot.session.calls
    assert not pair.audience.subscriptions.registered(99)

    await pair.handle(start(98, None))
    sent = list(pair.bot.session.messages.values())[-1]
    assert sent.chat.id == 98 and "Menu" in sent.text and sent.reply_markup is None
    user = pair.store.one("SELECT * FROM product_user_activity WHERE user_id=98")
    assert user["username"] is None and user["last_started_at"] is not None
    await pair.handle(Update.model_validate(update(owner=98, text="/menu")))
    assert list(pair.bot.session.messages.values())[-1].text == "You have no active subscriptions."
    assert not pair.audience.allowed(98)
    assert not pair.feeds["housing"].calls

    await pair.handle(start(98, "new_username"))
    assert (
        pair.store.one("SELECT username FROM product_user_activity WHERE user_id=98")["username"]
        == "new_username"
    )
    assert len(pair.store.rows("SELECT * FROM product_users WHERE user_id=98")) == 1
    assert not pair.store.rows("SELECT * FROM product_subscriptions WHERE user_id=98")


async def test_only_named_private_start_pins_numeric_identity(pair):
    await pair.handle(start())
    assert pair.audience.members()[0]["user_id"] == 99
    sent = list(pair.bot.session.messages.values())[-1]
    assert sent.chat.id == 99 and sent.reply_markup is None
    assert pair.store.one("SELECT 1 FROM subscription_pending WHERE user_id=99")
    await pair.handle(start(100))
    assert pair.audience.subscriptions.registered(100)
    assert not pair.audience.allowed(100)
    assert pair.audience.members()[0]["user_id"] == 99
    await pair.handle(start(99, "newusername"))
    assert pair.audience.allowed(99)


async def test_owner_can_subscribe_registered_user_and_menu_opens_enabled_topic(pair):
    await pair.handle(start(98, "new_guest"))
    await pair.handle(Update.model_validate(update(text="/menu")))
    deck = list(pair.bot.session.messages.values())[-1]
    await pair.handle(callback(deck, "manage:users"))
    users = list(pair.bot.session.messages.values())[-1]
    assert action(users, "@new_guest") == "manage:user:98"
    await pair.handle(callback(users, "manage:user:98"))
    user = list(pair.bot.session.messages.values())[-1]
    await pair.handle(callback(user, action(user, "Housing")))
    assert 98 in pair.audience.recipients(10)
    await pair.handle(Update.model_validate(update(owner=98, text="/menu")))
    guest = list(pair.bot.session.messages.values())[-1]
    assert guest.chat.id == 98
    assert action(guest, "Housing") == "housing:housing"
    assert "Settings" not in str(guest.reply_markup)


async def test_registered_user_lists_page_through_owner_settings(pair):
    with pair.store.db:
        for user_id in range(100, 125):
            pair.audience.subscriptions.register(user_id, None, 1000)
    await pair.handle(Update.model_validate(update(text="/menu")))
    deck = list(pair.bot.session.messages.values())[-1]
    await pair.handle(callback(deck, "manage:users"))
    users = list(pair.bot.session.messages.values())[-1]
    assert len(users.reply_markup.inline_keyboard) == 22
    await pair.handle(callback(users, action(users, "Next")))
    users = list(pair.bot.session.messages.values())[-1]
    assert action(users, "124") == "manage:user:124"
    assert action(users, "⬅️ Previous") == "manage:users:0"


async def test_start_registry_migrates_existing_users_and_survives_reopen(tmp_path):
    from personal_notifier.audience import HousingAudience
    from personal_notifier.store import BotStore

    settings = Settings(tmp_path, tmp_path / "run", tmp_path / "token", allowed_user_id=42)
    db_path = tmp_path / "bot.db"
    store = BotStore(db_path)
    with store.db:
        store.db.execute("CREATE TABLE product_users(user_id INTEGER PRIMARY KEY,label TEXT NOT NULL)")
        store.db.execute("INSERT INTO product_users VALUES(99,'existing')")
    audience = HousingAudience(settings, store)
    assert audience.subscriptions.registered(99)
    with store.db:
        audience.subscriptions.register(98, "recent", 1000)
        audience.subscriptions.register(98, "stale", 999)
    store.close()

    store = BotStore(db_path)
    try:
        audience = HousingAudience(settings, store)
        user = store.one("SELECT username,last_started_at FROM product_user_activity WHERE user_id=98")
        assert (user["username"], user["last_started_at"]) == ("recent", 1000)
        assert audience.subscriptions.registered(99)
        assert not audience.allowed(98)
        # The previous release can still write its original two-column table after rollback.
        with store.db:
            store.db.execute("INSERT OR IGNORE INTO product_users VALUES(42,'Owner')")
        assert audience.subscriptions.registered(42)
    finally:
        store.close()


async def test_tokens_are_bound_to_chat_even_when_message_ids_collide(pair):
    await enroll_housing(pair)
    owner = await pair.review.browse("housing", "queue")
    ctx = pair.review.recipient.set(99)
    try:
        pair.bot.session.counter = owner.message_id - 1
        guest = await pair.review.browse("housing", "queue")
    finally:
        pair.review.recipient.reset(ctx)
    assert guest.message_id == owner.message_id and guest.chat.id == 99
    assert len(pair.store.rows("SELECT * FROM review_screens WHERE message_id=?", (owner.message_id,))) == 2
    writes = len([c for c in pair.feeds["housing"].calls if c[2]])
    await pair.handle(callback(guest, action(owner, "Viewed"), owner=99))
    assert len([c for c in pair.feeds["housing"].calls if c[2]]) == writes


async def test_sort_cycles_and_stays_selected_on_navigation(pair):
    card = await pair.review.browse("housing", "queue")
    await pair.handle(callback(card, action(card, "Sort:")))
    card = pair.bot.session.messages[card.message_id]
    assert action(card, "Updated")
    await pair.handle(callback(card, action(card, "Sort:")))
    card = pair.bot.session.messages[card.message_id]
    assert action(card, "Rent ↑")
    await pair.handle(callback(card, action(card, "➡️")))
    card = pair.bot.session.messages[card.message_id]
    assert action(card, "Rent ↑")


async def test_each_recipient_gets_one_delivery_and_core_stays_owner_only(pair):
    from dataclasses import replace

    pair.settings = replace(pair.settings, core_enabled=True)
    await enroll_housing(pair)
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'🏠 Housing alert\n1 new · 3 in queue','',2,0)"
        )
        pair.store.db.execute("INSERT INTO notifier_notices VALUES(2,'session','Vibecoding notice',0,NULL)")
    before = len(pair.bot.session.calls)
    await pair.deliver()
    await pair.deliver()
    sends = [m for m in pair.bot.session.calls[before:] if isinstance(m, (SendMessage, SendPhoto))]
    assert [m.chat_id for m in sends] == [42, 99, 42]
    assert len(pair.store.rows("SELECT * FROM housing_receipts")) == 2


async def test_partial_failure_never_repeats_successful_recipient(pair):
    await enroll_housing(pair)
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'Housing alert','',2,0)"
        )
    original = pair.review.summary
    attempts = []

    async def flaky(source, text, recipient=None, event_id=None, new_listing=None):
        attempts.append(recipient)
        if recipient == 99 and attempts.count(99) == 1:
            raise TimeoutError()
        return await original(source, text, recipient, event_id=event_id, new_listing=new_listing)

    pair.review.summary = flaky
    await pair.deliver()
    await pair.deliver()
    assert attempts == [42, 99, 99]


async def test_guide_is_sent_only_once_and_has_queue_entry(pair):
    assert await pair.housing_guide(42) is True
    assert await pair.housing_guide(42) is False
    sent = list(pair.bot.session.messages.values())[-1]
    assert "Quick guide" in sent.text and "Sort" in sent.text
    assert action(sent, "View queue") == "browse:housing:queue"


async def test_owner_and_partner_counts_are_live_at_delivery_for_alerts_and_reminders(pair):
    await enroll_housing(pair)
    original = pair.feeds["housing"].queue_request
    totals = {"": 10, "99": 6}

    async def page(*args, **kwargs):
        result = await original(*args, **kwargs)
        result["total"] = totals[kwargs.get("actor", "")]
        return result

    pair.feeds["housing"].queue_request = page
    owner = await pair.review.summary("housing", "🏠 Housing alert\n2 new · 41 in queue", 42, event_id=1)
    partner = await pair.review.summary("housing", "🏠 Housing alert\n2 new · 41 in queue", 99, event_id=1)
    assert "2 new · 10 in queue" in owner.text
    assert "2 new · 6 in queue" in partner.text
    totals[""] = 3
    owner = await pair.review.summary("housing", "🏠 Housing alert\n2 new · 41 in queue", 42, event_id=1)
    assert "2 new · 3 in queue" in owner.text


async def test_empty_personal_queue_is_skipped_durably_without_blocking_other_person(pair):
    await enroll_housing(pair)
    original = pair.feeds["housing"].queue_request

    async def page(*args, **kwargs):
        result = await original(*args, **kwargs)
        result["total"] = 2 if kwargs.get("actor") == "99" else 0
        return result

    pair.feeds["housing"].queue_request = page
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'🏠 Housing alert\n2 new · 41 in queue','',2,0)"
        )
    before = len(pair.bot.session.calls)
    await pair.deliver()
    await pair.deliver()
    sends = [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert len(sends) == 1 and sends[0].chat_id == 99 and "2 in queue" in sends[0].text
    assert (
        pair.store.one("SELECT reason FROM housing_skips WHERE recipient=42")["reason"] == "no_live_new_items"
    )
    receipt_id = pair.store.one("SELECT telegram_id FROM housing_receipts WHERE recipient=99")["telegram_id"]
    assert pair.bot.session.messages[receipt_id].chat.id == 99
    assert pair.store.one("SELECT suppressed FROM feed_notices")["suppressed"] == 1


async def test_old_queue_does_not_make_a_removed_new_listing_alert_valid(pair):
    await enroll_housing(pair)
    original = pair.feeds["housing"].queue_request

    async def removed_new(*args, **kwargs):
        page = await original(*args, **kwargs)
        if kwargs.get("event_id"):
            page["new_total"] = 0
        return page

    pair.feeds["housing"].queue_request = removed_new
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'🏠 Housing alert\n1 new · 11 in queue','',2,0)"
        )
    before = len(pair.bot.session.calls)
    await pair.deliver()
    await pair.deliver()
    assert not [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert len(pair.store.rows("SELECT * FROM housing_skips WHERE event_id=1")) == 2
    assert pair.store.one("SELECT suppressed FROM feed_notices WHERE event_id=1")["suppressed"] == 1


async def test_only_recipient_who_still_has_the_new_listing_gets_an_alert(pair):
    await enroll_housing(pair)
    original = pair.feeds["housing"].queue_request

    async def personal(*args, **kwargs):
        page = await original(*args, **kwargs)
        if kwargs.get("event_id"):
            page["new_total"] = 1 if kwargs.get("actor") == "99" else 0
        return page

    pair.feeds["housing"].queue_request = personal
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'🏠 Housing alert\n3 new · 11 in queue','',2,0)"
        )
    before = len(pair.bot.session.calls)
    await pair.deliver()
    sends = [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert len(sends) == 1 and sends[0].chat_id == 99 and "1 new ·" in sends[0].text


async def test_opening_queue_from_digest_resets_price_order_to_publication(pair):
    from test_review_ui import action, callback

    pair.store.set("housing_sort:42:housing:queue", "price")
    digest = await pair.review.summary("housing", "Housing alert")
    await pair.handle(callback(digest, action(digest, "View queue")))
    card = pair.bot.session.messages[digest.message_id]
    assert action(card, "Published ↓")


async def test_management_owner_only_and_unsubscription_blocks_old_buttons(pair):
    await enroll_housing(pair)
    await pair.handle(Update.model_validate(update(text="/menu")))
    menu = list(pair.bot.session.messages.values())[-1]
    await pair.handle(callback(menu, "manage:home"))
    management = list(pair.bot.session.messages.values())[-1]
    assert "Settings" in management.text
    await pair.handle(callback(management, "manage:topic:0"))
    topic = list(pair.bot.session.messages.values())[-1]
    assert "rental_partner" in str(topic.reply_markup)
    await pair.handle(callback(topic, "manage:set:99:0:0:topic"))
    assert not pair.audience.subscriptions.allowed(99, "housing")
    before = len(pair.feeds["housing"].calls)
    await pair.handle(callback(topic, "browse:housing:queue", owner=99))
    assert len(pair.feeds["housing"].calls) == before
    await pair.handle(callback(topic, "manage:set:99:0:1:topic", owner=99))
    assert not pair.audience.subscriptions.allowed(99, "housing")


async def test_owner_can_reenable_subscription_after_hiding_all_queues(pair):
    pair.audience.subscriptions.set(42, 42, "housing", False)
    await pair.handle(Update.model_validate(update(text="/menu")))
    deck = list(pair.bot.session.messages.values())[-1]
    assert "Settings" in str(deck.reply_markup)
    assert "Housing" not in str(deck.reply_markup)
    await pair.handle(callback(deck, "manage:set:42:0:1:user"))
    assert pair.audience.subscriptions.allowed(42, "housing")


async def test_market_uses_same_collection_ui_and_scopes_as_housing(pair):
    from dataclasses import replace

    from personal_notifier.config import FeedSource

    pair.settings = replace(
        pair.settings,
        sources=pair.settings.sources
        + (
            FeedSource(
                "astronomy", pair.settings.runtime_dir / "api.sock", queue=True, topic="market.astronomy"
            ),
        ),
    )
    pair.feeds["astronomy"] = QueueFeed()
    await pair.handle(Update.model_validate(update(text="/menu")))
    deck = list(pair.bot.session.messages.values())[-1]
    assert "Market" in str(deck.reply_markup)
    await pair.handle(callback(deck, "market"))
    menu = list(pair.bot.session.messages.values())[-1]
    await pair.handle(callback(menu, "housing:astronomy"))
    collection = list(pair.bot.session.messages.values())[-1]
    assert "Astronomy" in collection.text
    assert "Favorites" in str(collection.reply_markup)
    await pair.handle(callback(collection, "browse:astronomy:queue"))
    card = list(pair.bot.session.messages.values())[-1]
    assert "Viewed" in str(card.reply_markup)
    assert "Favorite" in str(card.reply_markup)
    await enroll_housing(pair)
    before = len(pair.feeds["astronomy"].calls)
    await pair.handle(callback(card, "browse:astronomy:queue", owner=99))
    assert len(pair.feeds["astronomy"].calls) == before


async def test_forbidden_recipient_is_deferred_without_starving_owner_or_fake_receipt(pair):
    import time

    from aiogram.exceptions import TelegramForbiddenError

    await enroll_housing(pair)
    original = pair.review.summary
    blocked = True
    attempts = []

    async def send(source, text, recipient=None, event_id=None, new_listing=None):
        attempts.append(recipient)
        if recipient == 99 and blocked:
            raise TelegramForbiddenError(
                SendMessage(chat_id=99, text=text), "Forbidden: bot was blocked by the user"
            )
        return await original(source, text, recipient, event_id=event_id, new_listing=new_listing)

    pair.review.summary = send
    with pair.store.db:
        for event in range(1, 12):
            pair.store.db.execute(
                "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',?,'Housing alert','',2,?)",
                (event, event),
            )
    await pair.deliver()
    await pair.deliver()
    assert len(pair.store.rows("SELECT * FROM housing_receipts WHERE recipient=42")) == 11
    assert not pair.store.rows("SELECT * FROM housing_receipts WHERE recipient=99")
    assert attempts.count(99) == 11
    assert pair.store.one("SELECT MIN(retry_at) AS retry_at FROM feed_notices")["retry_at"] > time.time()
    before = len(attempts)
    await pair.deliver()
    assert len(attempts) == before
    blocked = False
    with pair.store.db:
        pair.store.db.execute("UPDATE feed_notices SET retry_at=0 WHERE event_id=1")
    await pair.deliver()
    assert len(pair.store.rows("SELECT * FROM housing_receipts WHERE recipient=42")) == 11
    assert len(pair.store.rows("SELECT * FROM housing_receipts WHERE recipient=99")) == 1
