"""Subscription migration and delivery authorization boundaries."""

import pytest
from aiogram.types import Update
from test_bot import update
from test_housing_audience import enroll_housing, start
from test_housing_audience import pair as _pair

from personal_notifier.subscriptions import Subscriptions

pair = _pair


async def test_migration_preserves_housing_member_and_default_denies_other_topics(pair):
    await enroll_housing(pair)
    subscriptions = Subscriptions(pair.store, 42)
    assert subscriptions.allowed(99, "housing")
    assert not subscriptions.allowed(99, "home.temperature")
    assert not subscriptions.allowed(99, "market.astronomy")
    assert subscriptions.allowed(42, "home.temperature")
    subscriptions.set(42, 99, "housing", False)
    assert not Subscriptions(pair.store, 42).allowed(99, "housing")


async def test_only_owner_may_change_subscriptions_and_disable_blocks_delivery(pair):
    await enroll_housing(pair)
    subscriptions = Subscriptions(pair.store, 42)
    with pytest.raises(PermissionError):
        subscriptions.set(99, 42, "housing", False)
    assert 99 in subscriptions.recipients("housing", "housing", 10)
    subscriptions.set(42, 99, "housing", False)
    assert 99 not in subscriptions.recipients("housing", "housing", 10)
    with pytest.raises(ValueError):
        subscriptions.set(42, 123, "housing", True)


async def test_resubscribe_skips_captured_backlog_per_source(pair):
    await enroll_housing(pair)
    subscriptions = pair.audience.subscriptions
    subscriptions.set(42, 99, "housing", False)
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',50,'old','',0,0)"
        )
    subscriptions.set(42, 99, "housing", True)
    assert 99 not in subscriptions.recipients("housing", "housing", 50)
    assert 99 in subscriptions.recipients("housing", "housing", 51)
    assert 99 in subscriptions.recipients("housing", "another-source", 1)


def event(identifier):
    return {
        "id": identifier,
        "type": "housing.queue.summary",
        "title": "New",
        "text": "New",
        "url": "",
        "priority": 1,
    }


async def test_enrollment_drains_uncaptured_producer_backlog_without_capturing(pair):
    calls = []

    async def read(cursor):
        calls.append(cursor)
        ids = range(cursor + 1, min(cursor + 100, 205) + 1)
        events = [event(identifier) for identifier in ids]
        return {"version": 1, "events": events, "next_cursor": events[-1]["id"] if events else cursor}

    pair.feeds["housing"].read = read
    await enroll_housing(pair)
    assert calls == [0, 100, 200]
    assert pair.store.get("feed_cursor:housing", "0") == "0"
    assert pair.store.rows("SELECT * FROM feed_notices") == []
    assert 99 not in pair.audience.recipients(205)
    assert 99 in pair.audience.recipients(206)


async def test_failed_first_enrollment_stays_closed_and_retries(pair):
    async def failed(cursor):
        raise OSError("Unavailable")

    pair.feeds["housing"].read = failed
    await enroll_housing(pair)
    assert not pair.audience.subscriptions.allowed(99, "housing")
    assert pair.store.one("SELECT 1 FROM subscription_pending WHERE user_id=99")

    async def recovered(cursor):
        return {"version": 1, "events": [], "next_cursor": cursor}

    pair.feeds["housing"].read = recovered
    await pair.handle(start())
    assert not pair.audience.subscriptions.allowed(99, "housing")
    await pair.handle(Update.model_validate(update(owner=99, text="/menu")))
    assert pair.audience.subscriptions.allowed(99, "housing")
    assert not pair.store.one("SELECT 1 FROM subscription_pending WHERE user_id=99")


async def test_outdoor_enrollment_is_owner_only_and_restart_preserves_opt_out(pair):
    from personal_notifier.subscriptions import Subscriptions

    await enroll_housing(pair)
    subs = pair.audience.subscriptions
    assert subs.allowed(42, "market.outdoor")
    assert not subs.allowed(99, "market.outdoor")
    subs.set(42, 42, "market.outdoor", False)
    resumed = Subscriptions(pair.store, 42)
    assert not resumed.allowed(42, "market.outdoor")
    assert resumed.allowed(99, "housing")


async def test_keyboard_subscription_is_owner_only_and_does_not_restore_opt_out(pair):
    app = pair
    from personal_notifier.subscriptions import Subscriptions

    subs = app.audience.subscriptions
    assert subs.allowed(42, "market.keyboards")
    assert not subs.allowed(99, "market.keyboards")
    subs.set(42, 42, "market.keyboards", False)
    resumed = Subscriptions(app.store, 42)
    assert not resumed.allowed(42, "market.keyboards")
