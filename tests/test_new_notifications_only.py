"""No queue reminders are captured or sent; genuine new discoveries still reach both users."""

from aiogram.methods import SendMessage
from test_housing_audience import enroll_housing
from test_housing_audience import pair as pair


async def test_capture_skips_reminders_but_delivers_new_members_to_both(pair):
    await enroll_housing(pair)

    async def read(cursor):
        events = (
            []
            if cursor
            else [
                dict(
                    id=1,
                    type="housing.queue.reminder",
                    title="Queue waiting",
                    text="3 waiting",
                    url="",
                    priority=0,
                ),
                dict(
                    id=2,
                    type="housing.queue.summary",
                    title="🏠 Housing alert",
                    text="2 new · 3 in queue",
                    url="",
                    priority=2,
                ),
            ]
        )
        return dict(version=1, events=events, next_cursor=2)

    pair.feeds["housing"].read = read
    before = len(pair.bot.session.calls)
    await pair.collect_feed(pair.settings.sources[0])
    await pair.deliver()
    await pair.collect_feed(pair.settings.sources[0])
    await pair.deliver()
    assert pair.store.get("feed_cursor:housing") == "2"
    assert not pair.store.one("SELECT * FROM feed_notices WHERE event_id=1")
    sent = [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert [m.chat_id for m in sent] == [42, 99]
    assert all("new ·" in m.text for m in sent)


async def test_pending_typed_and_legacy_reminders_are_suppressed_without_source_reads(pair):
    await enroll_housing(pair)
    with pair.store.db:
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created,event_type) VALUES('housing',1,'Queue waiting','',0,0,'housing.queue.reminder')"
        )
        pair.store.db.execute(
            "INSERT INTO feed_notices(source,event_id,body,url,priority,created) VALUES('housing',2,'🏠 Housing reminder\n3 waiting in your queue','',0,0)"
        )
    pair.feeds["housing"].calls.clear()
    before = len(pair.bot.session.calls)
    await pair.deliver()
    await pair.deliver()
    assert not pair.feeds["housing"].calls
    assert not [m for m in pair.bot.session.calls[before:] if isinstance(m, SendMessage)]
    assert pair.store.rows("SELECT telegram_id,suppressed FROM feed_notices ORDER BY event_id") == [
        dict(telegram_id=None, suppressed=1),
        dict(telegram_id=None, suppressed=1),
    ]
    assert await pair.review.summary("housing", "🏠 Housing reminder\n3 waiting in your queue", 42) is None
