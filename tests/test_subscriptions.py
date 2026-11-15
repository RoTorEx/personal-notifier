"""Subscription migration and delivery authorization boundaries."""

import pytest
from test_housing_audience import pair as _pair
from test_housing_audience import start

from personal_notifier.subscriptions import Subscriptions

pair = _pair


async def test_migration_preserves_housing_member_and_default_denies_other_topics(pair):
    await pair.handle(start())
    subscriptions = Subscriptions(pair.store, 42)
    assert subscriptions.allowed(99, "housing")
    assert not subscriptions.allowed(99, "home.temperature")
    assert not subscriptions.allowed(99, "market.astronomy")
    assert subscriptions.allowed(42, "home.temperature")
    subscriptions.set(42, 99, "housing", False)
    assert not Subscriptions(pair.store, 42).allowed(99, "housing")


async def test_only_owner_may_change_subscriptions_and_disable_blocks_delivery(pair):
    await pair.handle(start())
    subscriptions = Subscriptions(pair.store, 42)
    with pytest.raises(PermissionError):
        subscriptions.set(99, 42, "housing", False)
    assert 99 in subscriptions.recipients("housing", "housing", 10)
    subscriptions.set(42, 99, "housing", False)
    assert 99 not in subscriptions.recipients("housing", "housing", 10)
    with pytest.raises(ValueError):
        subscriptions.set(42, 123, "housing", True)


async def test_resubscribe_skips_captured_backlog_per_source(pair):
    await pair.handle(start())
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
