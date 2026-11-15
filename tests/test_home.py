"""Temperature boundaries, freshness, persistent cadence and per-user delivery."""

from dataclasses import replace

from test_housing_audience import pair as _pair

from personal_notifier.home import Home, advance, measurement

pair = _pair


def sample(t, at=1000):
    return {"id": str(at), "at": at * 1000, "received": at * 1000, "temperature": t}


def test_thresholds_periodic_cadence_oscillation_and_recovery():
    state, alert = advance({}, sample(15000), 1000)
    assert not alert
    state, alert = advance(state, sample(14900, 1060), 1060)
    assert alert and state["fast"] and state["reminder_at"] == 1360
    state, alert = advance(state, sample(14500, 1120), 1120)
    assert alert and state["reminder_at"] == 1360
    state, alert = advance(state, sample(14600, 1180), 1180)
    assert not alert
    state, alert = advance(state, sample(14500, 1240), 1240)
    assert not alert
    state, alert = advance(state, sample(14500, 1360), 1360)
    assert alert and state["reminder_at"] == 1660
    state, alert = advance(state, sample(15500, 1420), 1420)
    assert not alert and state["active"]
    state, alert = advance(state, sample(15500, 1420), 1480)
    assert state["warm"] == 1  # A duplicate cannot rearm.
    state, alert = advance(state, sample(15500, 1540), 1540)
    assert not alert and not state["active"] and not state["fast"]


def test_falling_temperature_accelerates_without_opening_alarm():
    state, _ = advance({}, sample(21000), 1000)
    state, alert = advance(state, sample(20900, 1600), 1600)
    assert state["fast"] and not alert


def test_missing_and_out_of_order_cannot_warn_or_recover():
    state, _ = advance({}, sample(14900), 1000)
    missing, alert = advance(state, None, 1400)
    assert not alert and missing["active"] and not missing["fresh"]
    older, alert = advance(missing, sample(16000, 900), 1400)
    assert not alert and older["active"] and not older["fresh"]


def test_measurement_never_uses_old_valid_fallback():
    event = {
        "clock_synchronized": True,
        "event_id": "reading",
        "measured_at_ms": 1000000,
        "data": {"temperature_millic": 14900, "error": None},
    }
    reading = {"event": event, "received_at_ms": 1000000}
    payload = {"freshness_seconds": 360, "sensor": {"latest": reading, "last_valid": reading}}
    assert measurement(payload, 1000)["temperature"] == 14900
    assert measurement(payload, 1361) is None
    payload["sensor"]["latest"] = None
    assert measurement(payload, 1000) is None


async def test_home_receipts_survive_restart_and_guest_is_not_subscribed(pair):
    pair.settings = replace(pair.settings, home_socket=pair.settings.runtime_dir / "metrics.sock")
    home = Home(pair)
    pair.home = home
    home.capture(sample(14900), 1000)
    await home.deliver(sample(14900), 1000)
    assert pair.store.one("SELECT recipient FROM home_receipts")["recipient"] == 42
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1
    resumed = Home(pair)
    resumed.capture(sample(14900, 1060), 1060)
    await resumed.deliver(sample(14900, 1060), 1060)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1
    resumed.capture(sample(14900, 1300), 1300)
    await resumed.deliver(sample(14900, 1300), 1300)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 2


def test_simultaneous_band_and_timer_make_one_alarm_and_large_jump_is_coalesced():
    state, _ = advance({}, sample(14900), 1000)
    state, alert = advance(state, sample(12500, 1300), 1300)
    assert alert and state["band"] == 5 and state["reminder_at"] == 1600
    state, alert = advance(state, sample(12600, 1360), 1360)
    assert not alert


async def test_stale_data_suppresses_retries_and_warm_data_stops_alarms(pair):
    home = Home(pair)
    home.capture(sample(14900), 1000)
    home.capture(None, 1060)
    await home.deliver(None, 1060)
    assert pair.store.rows("SELECT * FROM home_receipts") == []
    home.capture(sample(14900, 1120), 1120)
    await home.deliver(sample(14900, 1120), 1120)
    # Retry carries the current fresh measurement rather than the obsolete value.
    import json

    receipt = pair.store.one("SELECT sample FROM home_receipts")
    assert json.loads(receipt["sample"])["at"] == 1120000
    home.capture(sample(15000, 1300), 1300)
    await home.deliver(sample(15000, 1300), 1300)
    assert len(pair.store.rows("SELECT * FROM home_receipts")) == 1
