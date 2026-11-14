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


async def test_only_named_private_start_pins_numeric_identity(pair):
    await pair.handle(start(username="someoneelse"))
    await pair.handle(start(chat=-99))
    assert not pair.audience.members() and not pair.bot.session.calls
    await pair.handle(start())
    assert pair.audience.members()[0]["user_id"] == 99
    assert list(pair.bot.session.messages.values())[-1].chat.id == 99
    before = len(pair.bot.session.calls)
    await pair.handle(start(100))
    assert len(pair.bot.session.calls) == before
    # A pinned user's later username change does not transfer their identity.
    await pair.handle(start(99, "newusername"))
    assert pair.audience.allowed(99)


async def test_tokens_are_bound_to_chat_even_when_message_ids_collide(pair):
    await pair.handle(start())
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
    await pair.handle(start())
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
    await pair.handle(start())
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'Housing alert','',2,0)"
        )
    original = pair.review.summary
    attempts = []

    async def flaky(source, text, recipient=None):
        attempts.append(recipient)
        if recipient == 99 and attempts.count(99) == 1:
            raise TimeoutError()
        return await original(source, text, recipient)

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
    await pair.handle(start())
    original = pair.feeds["housing"].queue_request
    totals = {"": 10, "99": 6}

    async def page(*args, **kwargs):
        result = await original(*args, **kwargs)
        result["total"] = totals[kwargs.get("actor", "")]
        return result

    pair.feeds["housing"].queue_request = page
    owner = await pair.review.summary("housing", "🏠 Housing reminder\n41 waiting in your queue", 42)
    partner = await pair.review.summary("housing", "🏠 Housing alert\n2 new · 41 in queue", 99)
    assert "10 waiting in your queue" in owner.text
    assert "2 new · 6 in queue" in partner.text
    totals[""] = 3
    owner = await pair.review.summary("housing", "🏠 Housing alert\n2 new · 41 in queue", 42)
    assert "2 new · 3 in queue" in owner.text


async def test_empty_personal_queue_is_skipped_durably_without_blocking_other_person(pair):
    await pair.handle(start())
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
    assert pair.store.one("SELECT reason FROM housing_skips WHERE recipient=42")["reason"] == "empty_queue"
    receipt_id = pair.store.one("SELECT telegram_id FROM housing_receipts WHERE recipient=99")["telegram_id"]
    assert pair.bot.session.messages[receipt_id].chat.id == 99
    assert pair.store.one("SELECT suppressed FROM feed_notices")["suppressed"] == 1
