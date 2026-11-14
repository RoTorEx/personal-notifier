"""Notification-only Telegram process. Incoming content can never become agent input."""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import signal
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from personal_notifier.client import CoreClient, ReadOnlyCoreClient
from personal_notifier.config import Settings
from personal_notifier.feeds import FeedClient, validate_page
from personal_notifier.pacing import ChatPacer
from personal_notifier.schedule import reminders_allowed
from personal_notifier.store import BotStore

log = logging.getLogger(__name__)


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "unavailable"
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return (f"{hours}h " if hours else "") + (f"{minutes}m " if minutes or hours else "") + f"{seconds}s"


# One status vocabulary shared with the web list colours: green done, red needs review,
# yellow waiting for the owner, blue working.
OUTCOMES = {
    "completed": ("🟢", "Finished"),
    "finished": ("🟢", "Finished"),
    "failed": ("🔴", "Failed"),
    "error": ("🔴", "Failed"),
    "interrupted": ("🔴", "Interrupted"),
    "uncertain": ("🔴", "Outcome uncertain"),
}
STATUSES = {
    "idle": "Idle",
    "working": "Working",
    "connecting": "Working",
    "transcribing": "Transcribing voice",
    "waiting": "Waiting for you",
    "failed": "Failed",
    "interrupted": "Interrupted",
    "uncertain": "Outcome uncertain",
}


def compact_path(path: str) -> str:
    """Match the web list: the working directory and its parent."""
    return "/".join([part for part in path.split("/") if part][-2:]) or "/"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


class Notifier:
    def __init__(self, settings: Settings, bot=None, engine=None):
        self.settings = settings
        settings.validate_web_url()
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.store = BotStore(settings.data_dir / "bot.db")
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS notifier_notices(
                event_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, body TEXT NOT NULL,
                created REAL NOT NULL, telegram_id INTEGER);
            CREATE TABLE IF NOT EXISTS feed_notices(
                source TEXT NOT NULL,event_id INTEGER NOT NULL,body TEXT NOT NULL,
                url TEXT NOT NULL,priority INTEGER NOT NULL,created REAL NOT NULL,
                telegram_id INTEGER,PRIMARY KEY(source,event_id));
        """)
        columns = {row["name"] for row in self.store.db.execute("PRAGMA table_info(feed_notices)")}
        if "presentation" not in columns:
            with self.store.db:
                self.store.db.execute("ALTER TABLE feed_notices ADD COLUMN presentation TEXT")
        if "suppressed" not in columns:
            with self.store.db:
                self.store.db.execute(
                    "ALTER TABLE feed_notices ADD COLUMN suppressed INTEGER NOT NULL DEFAULT 0"
                )
        if not self.store.get("notifier_since"):
            self.store.set("notifier_since", str(time.time()))
        from personal_notifier.audience import HousingAudience

        self.audience = HousingAudience(settings, self.store)
        self.bot = bot or Bot(settings.read_token())
        if bot is None:
            self.bot.session.middleware.register(
                ChatPacer(self.store, settings.allowed_user_id, self.audience.allowed)
            )
        self.engine = ReadOnlyCoreClient(engine or CoreClient(settings))
        self.feeds = {source.name: FeedClient(source) for source in settings.sources}
        self.sessions: list[dict] = []
        self.live: dict = {}
        self.health: dict = {}
        self.stop = asyncio.Event()
        self.send_lock = asyncio.Lock()
        from personal_notifier.review import ReviewUI

        self.review = ReviewUI(self)
        instance_file = Path("/tmp/personal-notifier-instance")
        self.instance = instance_file.read_text().strip() if instance_file.exists() else uuid.uuid4().hex

    async def send(self, text: str, sid: str | None = None, silent: bool = False, url: str = ""):
        if sid:
            url = self.settings.web_url.rstrip("/") + "/#" + quote(sid, safe="")
        body = text[:3400] + ("\n" + url if url else "")
        async with self.send_lock:
            return await self.bot.send_message(
                self.settings.allowed_user_id,
                body,
                parse_mode=None,
                disable_web_page_preview=True,
                disable_notification=silent,
            )

    async def send_card(self, card):
        markup = None
        if card.get("copy_text"):
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📋 Copy phone", copy_text=CopyTextButton(text=card["copy_text"])
                        )
                    ]
                ]
            )
        async with self.send_lock:
            if card.get("photo_url"):
                try:
                    return await self.bot.send_photo(
                        self.settings.allowed_user_id,
                        card["photo_url"],
                        caption=card["html"],
                        show_caption_above_media=True,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                except TelegramBadRequest:
                    # An explicit rejection is safe to retry as text. Ambiguous transport
                    # errors retain the original queued card for normal retry.
                    log.info("Photo rejected; delivering the card as text")
            return await self.bot.send_message(
                self.settings.allowed_user_id,
                card["html"],
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )

    async def snapshot(self):
        self.health = await self.engine.call("/health")
        self.sessions = await self.engine.call("/sessions")
        self.live = await self.engine.call("/live")

    async def handle(self, update):
        return await self.review.handle(update)

    def record(self, key: str, value: str):
        self.store.db.execute(
            "INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def capture(self, event: dict):
        sid = event.get("session_id")
        if not sid:
            return
        start = float(self.store.get("notifier_since"))
        created = float(event.get("created", 0))
        key = "notifier_work:" + sid
        if event["id"] == 1:
            self.record("notifier_history_complete", "true")
        work = json.loads(
            self.store.get(
                key,
                json.dumps(
                    {
                        "started": None,
                        "inputs": 0,
                        "known": self.store.get("notifier_history_complete") == "true",
                    }
                ),
            )
        )
        if event["kind"] == "user":
            if work["started"] is None:
                work["started"] = created
            work["inputs"] += 1
            if created >= start:
                self.record("notifier_inputs", str(int(self.store.get("notifier_inputs", "0")) + 1))
            self.record(key, json.dumps(work))
            return
        if event["kind"] not in {"completed", "question"}:
            return
        seconds = (
            max(0, created - work["started"])
            if work["started"] is not None and work.get("known", False)
            else None
        )
        session = next((s for s in self.sessions if s["id"] == sid), {})
        if created >= start:
            payload = event.get("payload", {})
            if event["kind"] == "question":
                icon, label = "🟡", "Needs your input"
            else:
                status = payload.get("status", "finished")
                icon, label = OUTCOMES.get(status, ("🔴", status.capitalize()))
            cwd = session.get("cwd")
            # The session name leads: it is what the owner scans for in a notification list.
            text = (
                f"{icon} [Vibecoding] {session.get('name', sid)[:100]}\n"
                f"{label} · {self.settings.host_id} · {compact_path(cwd) if cwd else 'path unavailable'}\n"
                f"{session.get('model') or 'Auto'} · {session.get('effort') or 'default effort'} · "
                f"{session.get('collaboration_mode') or 'default'}\n"
                f"⏱ {duration(seconds) if seconds is not None else 'duration unavailable'} · "
                f"{plural(work['inputs'], 'message')} in this run"
            )
            self.store.db.execute(
                "INSERT OR IGNORE INTO notifier_notices(event_id,session_id,body,created) VALUES(?,?,?,?)",
                (event["id"], sid, text, created),
            )
            if event["kind"] == "completed":
                self.record("notifier_outcomes", str(int(self.store.get("notifier_outcomes", "0")) + 1))
                if seconds is not None:
                    self.record(
                        "notifier_seconds", str(float(self.store.get("notifier_seconds", "0")) + seconds)
                    )
        if event["kind"] == "completed":
            self.record(key, '{"started":null,"inputs":0,"known":true}')

    async def collect(self):
        # Core v1 pages at 100 events. Drain a finite backlog without delaying notices indefinitely.
        for _ in range(10):
            events = await self.engine.call("/events?after=" + self.store.get("notifier_cursor", "0"))
            for event in events:
                # Capture and cursor commit together; a crash cannot count/queue an event twice.
                with self.store.db:
                    self.capture(event)
                    self.record("notifier_cursor", str(event["id"]))
            if len(events) < 100:
                break

    async def collect_feed(self, source):
        cursor = int(self.store.get("feed_cursor:" + source.name, "0"))
        client = self.feeds[source.name]
        for _ in range(10):
            page = validate_page(await client.read(cursor), cursor)
            with self.store.db:
                for event in page["events"]:
                    if source.queue and not event["type"].endswith((".queue.summary", ".queue.reminder")):
                        continue
                    self.store.db.execute(
                        "INSERT OR IGNORE INTO feed_notices(source,event_id,body,url,priority,created,presentation) VALUES(?,?,?,?,?,?,?)",
                        (
                            source.name,
                            event["id"],
                            event["title"] + "\n" + event["text"],
                            event["url"],
                            event["priority"],
                            time.time(),
                            json.dumps(event["presentation"]) if "presentation" in event else None,
                        ),
                    )
                self.record("feed_cursor:" + source.name, str(page["next_cursor"]))
            log.info(
                "feed.captured source=%s events=%s cursor=%s",
                source.name,
                len(page["events"]),
                page["next_cursor"],
            )
            cursor = page["next_cursor"]
            if len(page["events"]) < 100:
                break

    async def deliver(self):
        # Merge sources into one paced queue; old Core receipts stay authoritative.
        rows = self.store.rows("""
            SELECT 'vibecoding' AS source,event_id,body,'' AS url,session_id,1 AS priority,created,NULL AS presentation
            FROM notifier_notices WHERE telegram_id IS NULL
            UNION ALL
            SELECT source,event_id,body,url,NULL AS session_id,priority,created,presentation
            FROM feed_notices WHERE telegram_id IS NULL AND suppressed=0
            ORDER BY priority DESC,created,event_id LIMIT 10
        """)
        queue_sources = {source.name for source in self.settings.sources if source.queue}
        for row in rows:
            if row["source"] in queue_sources:
                if (
                    row["body"].startswith(("🏠 Housing reminder", "Housing reminder"))
                    and not reminders_allowed()
                ):
                    with self.store.db:
                        self.store.db.execute(
                            "UPDATE feed_notices SET suppressed=1 WHERE source=? AND event_id=?",
                            (row["source"], row["event_id"]),
                        )
                    log.info("housing.reminder_suppressed source=%s event=%s", row["source"], row["event_id"])
                    continue
                pending = False
                owner_message = None
                for recipient in self.audience.recipients(row["event_id"]):
                    # Producer reminders are for the owner's queue. Guests have their own clock.
                    if recipient != self.settings.allowed_user_id and row["body"].startswith(
                        ("🏠 Housing reminder", "Housing reminder")
                    ):
                        continue
                    receipt = self.store.one(
                        "SELECT telegram_id FROM housing_receipts WHERE source=? AND event_id=? AND recipient=?",
                        (row["source"], row["event_id"], recipient),
                    )
                    skipped = self.store.one(
                        "SELECT 1 FROM housing_skips WHERE source=? AND event_id=? AND recipient=?",
                        (row["source"], row["event_id"], recipient),
                    )
                    if skipped:
                        continue
                    if receipt:
                        if recipient == self.settings.allowed_user_id:
                            owner_message = receipt["telegram_id"]
                        continue
                    try:
                        sent = await self.review.summary(row["source"], row["body"], recipient)
                        if sent is None:
                            with self.store.db:
                                self.store.db.execute(
                                    "INSERT OR IGNORE INTO housing_skips VALUES(?,?,?,?,?)",
                                    (row["source"], row["event_id"], recipient, "empty_queue", time.time()),
                                )
                            log.info(
                                "housing.empty_queue_skipped recipient=%s event=%s",
                                recipient,
                                row["event_id"],
                            )
                            continue
                        with self.store.db:
                            self.store.db.execute(
                                "INSERT OR IGNORE INTO housing_receipts VALUES(?,?,?,?)",
                                (row["source"], row["event_id"], recipient, sent.message_id),
                            )
                        self.store.set(f"housing_notice:{row['source']}:{recipient}", str(time.time()))
                        log.info(
                            "housing.delivered source=%s event=%s recipient=%s",
                            row["source"],
                            row["event_id"],
                            recipient,
                        )
                        if recipient == self.settings.allowed_user_id:
                            owner_message = sent.message_id
                    except Exception as error:
                        pending = True
                        log.warning(
                            "housing.delivery_failed recipient=%s error=%s", recipient, type(error).__name__
                        )
                if not pending:
                    with self.store.db:
                        if owner_message:
                            self.store.db.execute(
                                "UPDATE feed_notices SET telegram_id=? WHERE source=? AND event_id=?",
                                (owner_message, row["source"], row["event_id"]),
                            )
                        else:
                            # Per-recipient receipts/skips remain authoritative; no fake Telegram ID.
                            self.store.db.execute(
                                "UPDATE feed_notices SET suppressed=1 WHERE source=? AND event_id=?",
                                (row["source"], row["event_id"]),
                            )
                continue
            elif row["presentation"]:
                sent = await self.send_card(json.loads(row["presentation"]))
            else:
                sent = await self.send(row["body"], row["session_id"], url=row["url"])
            with self.store.db:
                if row["source"] == "vibecoding":
                    self.store.db.execute(
                        "UPDATE notifier_notices SET telegram_id=? WHERE event_id=?",
                        (sent.message_id, row["event_id"]),
                    )
                else:
                    self.store.db.execute(
                        "UPDATE feed_notices SET telegram_id=? WHERE source=? AND event_id=?",
                        (sent.message_id, row["source"], row["event_id"]),
                    )

    async def housing_guide(self, recipient):
        key = f"housing_guide:v1:{recipient}"
        if self.store.get(key):
            return False
        source = next((s.name for s in self.settings.sources if s.queue), None)
        if not source:
            return False
        text = (
            "🏠 Housing · Quick guide\n\n"
            "One queue for all selected areas.\n"
            "Only advertised rent is filtered; building fees are extra.\n\n"
            "View queue opens the listings. ⬅️ / ➡️ changes the card.\n"
            "✓ Viewed hides it from your queue. ☆ / ★ Favorite saves or unsaves it.\n"
            "Housing → Favorites opens saved listings. Unfavoriting keeps the current card for undo.\n"
            "↕️ Sort cycles Published / Updated / Rent ↑. The source button opens the ad.\n"
            "Back returns one screen; 🏠 Deck opens the main menu.\n\n"
            "Your Viewed and Favorites are personal. Scans: 10 min; notifications: 15 min; queue reminders: hourly, 12:00–00:00 Warsaw."
        )
        sent = await self.review.summary(source, text, recipient)
        self.store.set(key, str(sent.message_id))
        log.info("housing.guide_sent recipient=%s message=%s", recipient, sent.message_id)
        return True

    async def guest_reminders(self, source):
        if not reminders_allowed():
            return
        if self.store.one(
            "SELECT 1 FROM feed_notices WHERE source=? AND telegram_id IS NULL AND suppressed=0",
            (source.name,),
        ):
            return
        for member in self.audience.members():
            recipient = member["user_id"]
            key = f"housing_notice:{source.name}:{recipient}"
            previous = float(self.store.get(key, str(member["joined_at"])))
            if time.time() - previous < 3600:
                continue
            try:
                page = await self.feeds[source.name].queue_request(actor=str(recipient))
                if page["total"]:
                    sent = await self.review.summary(
                        source.name, f"🏠 Housing reminder\n{page['total']} waiting in your queue", recipient
                    )
                    if sent is None:
                        continue
                    self.store.set(key, str(time.time()))
                    log.info("housing.reminder recipient=%s total=%s", recipient, page["total"])
            except Exception as error:
                log.warning("housing.reminder_failed recipient=%s error=%s", recipient, type(error).__name__)

    async def pause(self, seconds):
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def core_loop(self):
        while not self.stop.is_set():
            try:
                await self.snapshot()
                await self.collect()
                self.store.set("source_success:vibecoding", str(time.time()))
            except Exception as error:
                log.warning("Vibecoding collection will retry: %s", type(error).__name__)
            await self.pause(3)

    async def feed_loop(self, source):
        while not self.stop.is_set():
            if source.queue:
                await self.pause(source.poll_seconds - time.time() % source.poll_seconds)
                if self.stop.is_set():
                    break
            try:
                log.info("feed.poll_started source=%s", source.name)
                await self.collect_feed(source)
                if source.queue:
                    await self.guest_reminders(source)
                self.store.set("source_success:" + source.name, str(time.time()))
            except Exception as error:
                log.warning("Source %s will retry: %s", source.name, type(error).__name__)
            if not source.queue:
                await self.pause(source.poll_seconds)

    async def notifications(self):
        # Delivery is independent of slow or unavailable source requests.
        while not self.stop.is_set():
            try:
                await self.deliver()
            except Exception as error:
                log.warning("Delivery will retry: %s", type(error).__name__)
            self.store.set("poll_heartbeat", str(time.time()))
            await self.pause(1)

    async def updates_loop(self):
        while not self.stop.is_set():
            try:
                updates = await self.bot.get_updates(
                    offset=int(self.store.get("review_update_offset", "0")),
                    timeout=20,
                    allowed_updates=["callback_query", "message"],
                    request_timeout=30,
                )
                for update in updates:
                    await self.handle(update)
                    self.store.set("review_update_offset", str(update.update_id + 1))
            except Exception as error:
                log.warning("Owner review will retry: %s", type(error).__name__)
                await self.pause(2)

    async def run(self):
        lock = (self.settings.data_dir / "notifier.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError("Another notifier owns this state directory") from None
        self.store.set("bot_pid", str(os.getpid()))
        self.store.set("bot_instance", self.instance)
        self.store.set("poll_heartbeat", str(time.time()))
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, self.stop.set)
        try:
            identity = await self.bot.get_me()
            if self.settings.bot_username and identity.username != self.settings.bot_username:
                raise ValueError("Notifier token belongs to an unexpected bot")
            queue_enabled = any(source.queue for source in self.settings.sources)
            if queue_enabled:
                await self.bot.delete_my_commands()
                await self.bot.set_my_commands(
                    [
                        BotCommand(command="menu", description="Home deck"),
                        BotCommand(command="vibecoding", description="Vibecoding"),
                        BotCommand(command="housing", description="Housing"),
                    ],
                    scope=BotCommandScopeChat(chat_id=self.settings.allowed_user_id),
                )
            else:
                await self.bot.delete_my_commands()
            if queue_enabled:
                for recipient in [self.settings.allowed_user_id] + [
                    m["user_id"] for m in self.audience.members()
                ]:
                    try:
                        await self.housing_guide(recipient)
                    except Exception as error:
                        log.warning(
                            "housing.guide_failed recipient=%s error=%s", recipient, type(error).__name__
                        )
            tasks = [asyncio.create_task(self.notifications())]
            if queue_enabled:
                tasks.append(asyncio.create_task(self.updates_loop()))
            if self.settings.core_enabled:
                tasks.append(asyncio.create_task(self.core_loop()))
            tasks.extend(asyncio.create_task(self.feed_loop(source)) for source in self.settings.sources)
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await self.engine.close()
            for client in self.feeds.values():
                await client.close()
            await self.bot.session.close()
            self.store.close()
            lock.close()


async def run(settings: Settings):
    await Notifier(settings).run()
