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
            CREATE TABLE IF NOT EXISTS housing_receipts(
                source TEXT NOT NULL,event_id INTEGER NOT NULL,recipient INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,PRIMARY KEY(source,event_id,recipient));
        """)

    def members(self):
        return [
            row
            for row in self.store.rows("SELECT * FROM housing_members WHERE active=1")
            if row["username"] in self.settings.housing_usernames
        ]

    def allowed(self, user_id):
        return user_id == self.settings.allowed_user_id or any(
            r["user_id"] == user_id for r in self.members()
        )

    def authorize(self, sender, message, callback):
        if not sender or message.chat.type != "private" or message.chat.id != sender.id or sender.is_bot:
            return False
        if self.allowed(sender.id):
            return True
        username = (sender.username or "").lower()
        if (
            callback
            or (message.text or "").split("@", 1)[0] != "/start"
            or username not in self.settings.housing_usernames
        ):
            return False
        pinned = self.store.one("SELECT * FROM housing_members WHERE username=?", (username,))
        if pinned and pinned["user_id"] != sender.id:
            return False
        watermark = self.store.one("SELECT COALESCE(MAX(event_id),0) AS id FROM feed_notices")["id"]
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO housing_members(username,user_id,joined_event_id,joined_at) VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET active=1",
                (username, sender.id, watermark, time.time()),
            )
        log.info("housing.member_joined recipient=%s", sender.id)
        return True

    def recipients(self, event_id):
        return [self.settings.allowed_user_id] + [
            r["user_id"] for r in self.members() if event_id > r["joined_event_id"]
        ]
