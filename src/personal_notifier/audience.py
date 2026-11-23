"""Pinned housing recipients; a username authorizes only the first private /start."""

import logging
import time

log = logging.getLogger(__name__)


class HousingAudience:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        store.db.executescript("""
            CREATE TABLE IF NOT EXISTS housing_members(
                username TEXT PRIMARY KEY,user_id INTEGER UNIQUE NOT NULL,
                joined_event_id INTEGER NOT NULL,joined_at REAL NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS housing_skips(
                source TEXT NOT NULL,event_id INTEGER NOT NULL,recipient INTEGER NOT NULL,
                reason TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(source,event_id,recipient));
            CREATE TABLE IF NOT EXISTS housing_receipts(
                source TEXT NOT NULL,event_id INTEGER NOT NULL,recipient INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,PRIMARY KEY(source,event_id,recipient));
        """)

        from personal_notifier.subscriptions import Subscriptions

        self.subscriptions = Subscriptions(store, settings.allowed_user_id)

    def members(self):
        return [
            row
            for row in self.store.rows("SELECT * FROM housing_members WHERE active=1")
            if row["username"] in self.settings.housing_usernames
        ]

    def allowed(self, user_id):
        if user_id == self.settings.allowed_user_id:
            return True
        pin = self.store.one("SELECT username,active FROM housing_members WHERE user_id=?", (user_id,))
        if pin:
            return pin["active"] == 1 and pin["username"] in self.settings.housing_usernames
        return self.subscriptions.has_active(user_id)

    def start(self, sender, started_at):
        username = (sender.username or "").lower()
        with self.store.db:
            self.subscriptions.register(sender.id, sender.username, started_at)
            if sender.id == self.settings.allowed_user_id or username not in self.settings.housing_usernames:
                return
            pins = self.store.rows(
                "SELECT username,user_id,active FROM housing_members WHERE username=? OR user_id=?",
                (username, sender.id),
            )
            if any(
                pin["username"] != username or pin["user_id"] != sender.id or pin["active"] for pin in pins
            ):
                return
            watermark = self.store.one("SELECT COALESCE(MAX(event_id),0) AS id FROM feed_notices")["id"]
            self.store.db.execute(
                "INSERT INTO housing_members(username,user_id,joined_event_id,joined_at) VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET active=1",
                (username, sender.id, watermark, time.time()),
            )
            self.subscriptions.enroll(sender.id, username)
        log.info("housing.member_joined recipient=%s", sender.id)

    def recipients(self, event_id, source="housing", topic="housing"):
        owner = self.settings.allowed_user_id
        eligible = self.subscriptions.recipients(topic, source, event_id)
        joined = {member["user_id"]: member["joined_event_id"] for member in self.members()}
        return ([owner] if owner in eligible else []) + [
            user_id
            for user_id in eligible
            if user_id != owner
            and self.allowed(user_id)
            and (topic != "housing" or event_id > joined.get(user_id, 0))
        ]
