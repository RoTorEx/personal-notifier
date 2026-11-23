"""Temperature boundaries, freshness, persistent cadence and per-user delivery."""

from dataclasses import replace

from test_housing_audience import pair as _pair
from test_housing_audience import start
from test_review_ui import callback

from personal_notifier.home import Home, advance, body, format_temperature, measurement

pair = _pair


def sample(t, at=1000):
    return {"id": str(at), "at": at * 1000, "received": at * 1000, "temperature": t}


def test_temperature_display_rounds_to_tenths_without_changing_alarm_threshold():
    assert format_temperature(14388) == "14.4 °C"
    assert format_temperature(14400) == "14.4 °C"
    assert format_temperature(14000) == "14.0 °C"
    assert format_temperature(14350) == "14.4 °C"
    assert format_temperature(-14350) == "-14.4 °C"
    assert "9.8 °C · threshold 10 °C" in body(sample(9824))
    assert "10.0 °C (rounded) · threshold 10 °C" in body(sample(9999))
    assert advance({}, sample(9999), 1000)[1]
    assert not advance({}, sample(10000), 1000)[1]


async def test_home_menu_shows_the_same_rounded_reading(pair):
    import time

    pair.settings = replace(pair.settings, home_socket=pair.settings.runtime_dir / "metrics.sock")
    pair.home = Home(pair)
    now = int(time.time())
    pair.home.capture(sample(14388, now), now)

    deck = await pair.review.home()
    await pair.handle(callback(deck, "home:temperature"))
    view = pair.bot.session.messages[deck.message_id]
    assert "14.4 °C" in view.text
    assert "14.388" not in view.text


def test_thresholds_periodic_cadence_oscillation_and_recovery():
    state, alert = advance({}, sample(10000), 1000)
    assert not alert
    state, alert = advance(state, sample(9900, 1060), 1060)
    assert alert and state["fast"] and state["reminder_at"] == 1360
    state, alert = advance(state, sample(9500, 1120), 1120)
    assert alert and state["reminder_at"] == 1360
    state, alert = advance(state, sample(9600, 1180), 1180)
    assert not alert
    state, alert = advance(state, sample(9500, 1240), 1240)
    assert not alert
    state, alert = advance(state, sample(9500, 1360), 1360)
    assert alert and state["reminder_at"] == 1660
    state, alert = advance(state, sample(10500, 1420), 1420)
    assert not alert and state["active"]
    state, alert = advance(state, sample(10500, 1420), 1480)
    assert state["warm"] == 1  # A duplicate cannot rearm.
    state, alert = advance(state, sample(10500, 1540), 1540)
    assert not alert and not state["active"] and not state["fast"]


def test_existing_incident_is_reclassified_against_the_new_threshold():
    legacy = {
        "active": True,
        "band": 9,
        "fast": True,
        "warm": 1,
        "reminder_at": 1001,
        "sample": sample(14000),
    }
    state, alert = advance(legacy, legacy["sample"], 1060)
    assert not alert and not state["active"] and state["reminder_at"] is None

    legacy["sample"] = sample(9900)
    state, alert = advance(legacy, legacy["sample"], 1060)
    assert alert and state["band"] == 0 and state["reminder_at"] == 1360


def test_falling_temperature_accelerates_without_opening_alarm():
    state, _ = advance({}, sample(21000), 1000)
    state, alert = advance(state, sample(20900, 1600), 1600)
    assert state["fast"] and not alert


def test_missing_and_out_of_order_cannot_warn_or_recover():
    state, _ = advance({}, sample(9900), 1000)
    missing, alert = advance(state, None, 1400)
    assert not alert and missing["active"] and not missing["fresh"]
    older, alert = advance(missing, sample(16000, 900), 1400)
    assert not alert and older["active"] and not older["fresh"]


def test_measurement_never_uses_old_valid_fallback():
    event = {
        "clock_synchronized": True,
        "event_id": "reading",
        "measured_at_ms": 1000000,
        "data": {"temperature_millic": 9900, "error": None},
    }
    reading = {"event": event, "received_at_ms": 1000000}
    payload = {"freshness_seconds": 360, "sensor": {"latest": reading, "last_valid": reading}}
    assert measurement(payload, 1000)["temperature"] == 9900
    assert measurement(payload, 1361) is None
    payload["sensor"]["latest"] = None
    assert measurement(payload, 1000) is None


async def test_home_receipts_survive_restart_and_guest_is_not_subscribed(pair):
    pair.settings = replace(pair.settings, home_socket=pair.settings.runtime_dir / "metrics.sock")
    home = Home(pair)
    pair.home = home
    await pair.handle(start())
    assert pair.audience.allowed(99)
    assert not pair.audience.subscriptions.allowed(99, "home.temperature")
    home.capture(sample(9900), 1000)
    await home.deliver(sample(9900), 1000)
    assert pair.store.one("SELECT recipient FROM home_receipts")["recipient"] == 42
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1
    resumed = Home(pair)
    resumed.capture(sample(9900, 1060), 1060)
    await resumed.deliver(sample(9900, 1060), 1060)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1
    resumed.capture(sample(9900, 1300), 1300)
    await resumed.deliver(sample(9900, 1300), 1300)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 2


def test_simultaneous_band_and_timer_make_one_alarm_and_large_jump_is_coalesced():
    state, _ = advance({}, sample(9900), 1000)
    state, alert = advance(state, sample(7500, 1300), 1300)
    assert alert and state["band"] == 5 and state["reminder_at"] == 1600
    state, alert = advance(state, sample(7600, 1360), 1360)
    assert not alert


async def test_stale_data_suppresses_retries_and_warm_data_stops_alarms(pair):
    home = Home(pair)
    home.capture(sample(9900), 1000)
    home.capture(None, 1060)
    await home.deliver(None, 1060)
    assert pair.store.rows("SELECT * FROM home_receipts") == []
    home.capture(sample(9900, 1120), 1120)
    await home.deliver(sample(9900, 1120), 1120)
    # Retry carries the current fresh measurement rather than the obsolete value.
    import json

    receipt = pair.store.one("SELECT sample FROM home_receipts")
    assert json.loads(receipt["sample"])["at"] == 1120000
    home.capture(sample(10000, 1300), 1300)
    await home.deliver(sample(10000, 1300), 1300)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1


async def test_climate_read_waits_for_all_http_chunks(pair):
    import json
    import tempfile
    from pathlib import Path

    from aiohttp import web

    payload = {"freshness_seconds": 360, "sensor": None, "history": [None] * 10000}
    raw = json.dumps(payload).encode()

    async def chunks(request):
        import asyncio

        response = web.StreamResponse(headers={"Content-Type": "application/json"})
        await response.prepare(request)
        await response.write(raw[:80])
        await asyncio.sleep(0.01)
        await response.write(raw[80:])
        await response.write_eof()
        return response

    with tempfile.TemporaryDirectory(prefix="home-read-", dir="/tmp") as directory:
        app = web.Application()
        app.router.add_get("/api/v1/climate", chunks)
        runner = web.AppRunner(app)
        await runner.setup()
        socket = Path(directory) / "read.sock"
        await web.UnixSite(runner, str(socket)).start()
        pair.settings = replace(pair.settings, home_socket=socket)
        home = Home(pair)
        try:
            assert await home.read() == payload
        finally:
            await home.close()
            await runner.cleanup()


async def test_alarm_cadence_after_database_reopen_has_no_replay_burst(pair):
    from personal_notifier.audience import HousingAudience
    from personal_notifier.store import BotStore

    home = Home(pair)
    home.capture(sample(9900), 1000)
    await home.deliver(sample(9900), 1000)
    path = pair.settings.data_dir / "bot.db"
    pair.store.close()
    pair.store = BotStore(path)
    pair.audience = HousingAudience(pair.settings, pair.store)
    resumed = Home(pair)
    resumed.capture(sample(9900, 1180), 1180)
    await resumed.deliver(sample(9900, 1180), 1180)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1
    resumed.capture(sample(9900, 2200), 2200)
    await resumed.deliver(sample(9900, 2200), 2200)
    await resumed.deliver(sample(9900, 2200), 2200)
    rows = pair.store.rows("SELECT * FROM home_receipts")
    assert len(rows) == 2 and all(row["recipient"] == 42 for row in rows)
    assert "remains below" in pair.store.one("SELECT body FROM home_notices ORDER BY id DESC LIMIT 1")["body"]
