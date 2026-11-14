"""Delivery-time suppression never blocks new housing events or replays old reminders."""

from datetime import datetime
from unittest.mock import patch

from aiogram.methods import SendMessage
from test_housing_audience import pair as pair
from test_housing_audience import start

from personal_notifier.schedule import reminders_allowed


def test_warsaw_reminder_window_uses_seasonal_offset():
    for at, expected in [
        ("2026-11-14T10:59:59+00:00", False),
        ("2026-11-14T11:00:00+00:00", True),
        ("2026-11-14T23:00:00+00:00", False),
        ("2026-07-14T10:00:00+00:00", True),
        ("2026-07-14T22:00:00+00:00", False),
    ]:
        assert reminders_allowed(datetime.fromisoformat(at)) is expected


async def test_night_suppresses_queued_reminder_but_delivers_new_alert_to_both(pair):
    await pair.handle(start())
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',1,'🏠 Housing reminder\nQueue waiting','',0,0)"
        )
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',2,'🏠 Housing alert\n1 new · 3 in queue','',2,0)"
        )
    before = len(pair.bot.session.calls)
    with patch("personal_notifier.notifier.reminders_allowed", return_value=False):
        await pair.deliver()
    sends = [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert [m.chat_id for m in sends] == [42, 99]
    reminder = pair.store.one("SELECT telegram_id,suppressed FROM feed_notices WHERE event_id=1")
    assert reminder == {"telegram_id": None, "suppressed": 1}
    with patch("personal_notifier.notifier.reminders_allowed", return_value=True):
        await pair.deliver()
    assert len([m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]) == 2


async def test_guest_reminder_checks_window_before_source_read_and_sends_once_when_open(pair):
    await pair.handle(start())
    with pair.store.db:
        pair.store.db.execute("UPDATE housing_members SET joined_at=0")
    source = pair.settings.sources[0]
    pair.feeds["housing"].calls.clear()
    with patch("personal_notifier.notifier.reminders_allowed", return_value=False):
        await pair.guest_reminders(source)
    assert not pair.feeds["housing"].calls
    before = len(pair.bot.session.calls)
    with patch("personal_notifier.notifier.reminders_allowed", return_value=True):
        await pair.guest_reminders(source)
        await pair.guest_reminders(source)
    sends = [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert len(sends) == 1 and sends[0].chat_id == 99 and "Housing reminder" in sends[0].text
