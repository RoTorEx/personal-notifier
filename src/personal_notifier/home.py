"""Indoor temperature rules, durable alarm state and bounded telemetry reads."""

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout, UnixConnector

log = logging.getLogger(__name__)

COLD_THRESHOLD_MILLIC = 10_000
TEMPERATURE_STEP_MILLIC = 500
RECOVERY_THRESHOLD_MILLIC = COLD_THRESHOLD_MILLIC + TEMPERATURE_STEP_MILLIC


def measurement(payload, now):
    limit = payload.get("freshness_seconds")
    if type(limit) is not int or not 30 <= limit <= 86400:
        return None
    reading = (payload.get("sensor") or {}).get("latest")
    if not isinstance(reading, dict):
        return None
    event = reading.get("event") or {}
    data = event.get("data") or {}
    measured, received = event.get("measured_at_ms"), reading.get("received_at_ms")
    temperature = data.get("temperature_millic")
    if (
        event.get("clock_synchronized") is not True
        or data.get("error") is not None
        or type(temperature) is not int
        or not -80000 <= temperature <= 100000
        or type(measured) is not int
        or type(received) is not int
        or not -30000 <= now * 1000 - measured <= limit * 1000
        or not 0 <= now * 1000 - received <= limit * 1000
    ):
        return None
    return {
        "id": str(event.get("event_id") or measured),
        "at": measured,
        "received": received,
        "temperature": temperature,
        "valid_until": min(measured, received) + limit * 1000,
    }


def advance(state, sample, now):
    state = dict(state)
    if not sample:
        state["fresh"] = False
        return state, False
    previous = state.get("sample")
    distinct = previous is None or sample["at"] > previous["at"]
    if previous and (
        sample["at"] < previous["at"]
        or (sample["at"] == previous["at"] and sample != previous)
        or (sample["id"] == previous["id"] and sample != previous)
    ):
        state["fresh"] = False
        return state, False
    threshold_changed = state.get("threshold_millic") != COLD_THRESHOLD_MILLIC
    if threshold_changed:
        # Stored bands and recovery counts were relative to the old threshold.
        state.update(active=False, warm=0, band=None, reminder_at=None)
        state["threshold_millic"] = COLD_THRESHOLD_MILLIC
    state["fresh"] = True
    temperature = sample["temperature"]
    alert = False
    if distinct or threshold_changed:
        falling = distinct and previous is not None and temperature < previous["temperature"]
        warm = temperature >= RECOVERY_THRESHOLD_MILLIC and not falling
        state["warm"] = state.get("warm", 0) + 1 if warm else 0
        state["fast"] = bool(state.get("fast") or falling or temperature < COLD_THRESHOLD_MILLIC)
        if state["warm"] >= 2:
            state.update(active=False, fast=False, band=None, reminder_at=None)
        if temperature < COLD_THRESHOLD_MILLIC:
            # Subsequent bands include their boundary.
            band = (COLD_THRESHOLD_MILLIC - temperature) // TEMPERATURE_STEP_MILLIC
            alert = not state.get("active") or band > state.get("band", -1)
            state["active"] = True
            state["band"] = max(band, state.get("band") or 0)
            if state.get("reminder_at") is None:
                state["reminder_at"] = now + 300
        state["sample"] = sample
    if (
        temperature < COLD_THRESHOLD_MILLIC
        and state.get("active")
        and now >= (state.get("reminder_at") or now + 300)
    ):
        alert = True
        state["reminder_at"] = now + 300
    return state, alert


def format_temperature(temperature_millic):
    tenths = (abs(temperature_millic) + 50) // 100
    if temperature_millic < 0:
        tenths = -tenths
    return f"{tenths / 10:.1f} °C"


def body(sample, previous_temperature=None):
    lower = previous_temperature is not None and sample["temperature"] < previous_temperature
    label = "Temperature decreased" if lower else "Temperature remains below threshold"
    at = datetime.fromtimestamp(sample["at"] / 1000, ZoneInfo("Europe/Warsaw"))
    reading = format_temperature(sample["temperature"])
    if reading == format_temperature(COLD_THRESHOLD_MILLIC):
        reading += " (rounded)"
    return (
        "🌡🚨 Temperature alarm\n\n"
        + label
        + f"\n{reading} · threshold {COLD_THRESHOLD_MILLIC / 1000:g} °C"
        + "\nMeasured: "
        + at.strftime("%d.%m.%Y %H:%M %Z")
        + " (UTC"
        + at.strftime("%z")[:3]
        + ":"
        + at.strftime("%z")[3:]
        + ")"
    )


class Home:
    def __init__(self, app):
        self.app = app
        self.http = None
        app.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS home_notices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT NOT NULL,
                sample TEXT NOT NULL,created REAL NOT NULL,superseded INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS home_receipts(
                event_id INTEGER NOT NULL,recipient INTEGER NOT NULL,telegram_id INTEGER NOT NULL,sample TEXT NOT NULL,
                PRIMARY KEY(event_id,recipient));
        """)

    @property
    def state(self):
        return json.loads(self.app.store.get("home:state", "{}"))

    async def read(self):
        if self.http is None:
            self.http = ClientSession(
                connector=UnixConnector(path=str(self.app.settings.home_socket)),
                timeout=ClientTimeout(total=10),
            )
        async with self.http.get("http://node-tools/api/v1/climate") as response:
            response.raise_for_status()
            from personal_notifier.feeds import bounded_json

            return await bounded_json(response, 1_000_000)

    def capture(self, sample, now):
        state, alert = advance(self.state, sample, now)
        with self.app.store.db:
            # Pending old readings never become warnings about the current home.
            self.app.store.db.execute("UPDATE home_notices SET superseded=1 WHERE superseded=0")
            if alert:
                self.app.store.db.execute(
                    "INSERT INTO home_notices(body,sample,created) VALUES(?,?,?)",
                    (body(sample, state.get("last_reported")), json.dumps(sample), now),
                )
            elif sample and state.get("fresh") and sample["temperature"] < COLD_THRESHOLD_MILLIC:
                # Preserve a still-current undelivered alarm across transient send failures.
                row = self.app.store.one("SELECT id,sample FROM home_notices ORDER BY id DESC LIMIT 1")
                pending = row and any(
                    not self.app.store.one(
                        "SELECT 1 FROM home_receipts WHERE event_id=? AND recipient=?", (row["id"], recipient)
                    )
                    for recipient in self.app.audience.subscriptions.recipients(
                        "home.temperature", "home", row["id"]
                    )
                )
                if pending:
                    self.app.store.db.execute(
                        "UPDATE home_notices SET superseded=0,body=?,sample=? WHERE id=?",
                        (body(sample), json.dumps(sample), row["id"]),
                    )
            self.app.store.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('home:state',?)", (json.dumps(state),)
            )
        return state

    async def deliver(self, sample, now):
        row = self.app.store.one("SELECT * FROM home_notices WHERE superseded=0 ORDER BY id DESC LIMIT 1")
        if (
            not row
            or not sample
            or not self.state.get("fresh")
            or sample["temperature"] >= COLD_THRESHOLD_MILLIC
        ):
            return
        for recipient in self.app.audience.subscriptions.recipients("home.temperature", "home", row["id"]):
            if not self.app.audience.allowed(recipient) or self.app.store.one(
                "SELECT 1 FROM home_receipts WHERE event_id=? AND recipient=?", (row["id"], recipient)
            ):
                continue
            previous = self.app.store.one(
                "SELECT sample FROM home_receipts WHERE recipient=? ORDER BY event_id DESC LIMIT 1",
                (recipient,),
            )
            prior_temperature = json.loads(previous["sample"])["temperature"] if previous else None
            try:
                async with self.app.send_lock:
                    if not self.app.audience.subscriptions.allowed(recipient, "home.temperature"):
                        continue
                    sent = await self.app.bot.send_message(recipient, body(sample, prior_temperature))
            except Exception as error:
                log.warning(
                    "home.delivery_failed recipient=%s event=%s error=%s",
                    recipient,
                    row["id"],
                    type(error).__name__,
                )
                continue
            with self.app.store.db:
                self.app.store.db.execute(
                    "INSERT INTO home_receipts VALUES(?,?,?,?)",
                    (row["id"], recipient, sent.message_id, json.dumps(sample)),
                )
                state = self.state
                state["last_reported"] = sample["temperature"]
                self.app.store.db.execute(
                    "INSERT OR REPLACE INTO meta VALUES('home:state',?)", (json.dumps(state),)
                )

    async def close(self):
        if self.http:
            await self.http.close()
