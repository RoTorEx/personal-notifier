"""Product topic permissions and per-source subscription watermarks."""

TOPICS = {
    "housing": "🏠 Housing",
    "market.astronomy": "🔭 Astronomy",
    "market.digital_pianos": "🎹 Digital pianos",
    "home.temperature": "🌡 Home temperature",
    "market.outdoor": "🏕 Outdoor",
    "market.keyboards": "⌨️ Keyboards",  # Append to preserve management callback indices.
}


class Subscriptions:
    def __init__(self, store, owner):
        self.store, self.owner = store, owner
        store.db.executescript("""
            CREATE TABLE IF NOT EXISTS product_users(
                user_id INTEGER PRIMARY KEY, label TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS product_subscriptions(
                user_id INTEGER NOT NULL,topic TEXT NOT NULL,enabled INTEGER NOT NULL,
                PRIMARY KEY(user_id,topic));
            CREATE TABLE IF NOT EXISTS subscription_pending(
                user_id INTEGER NOT NULL,topic TEXT NOT NULL,PRIMARY KEY(user_id,topic));
            CREATE TABLE IF NOT EXISTS subscription_watermarks(
                user_id INTEGER NOT NULL,topic TEXT NOT NULL,source TEXT NOT NULL,event_id INTEGER NOT NULL,
                PRIMARY KEY(user_id,topic,source));
            CREATE TABLE IF NOT EXISTS muted_alerts(
                user_id INTEGER NOT NULL,topic TEXT NOT NULL,PRIMARY KEY(user_id,topic));
        """)
        with store.db:
            store.db.execute("INSERT OR IGNORE INTO product_users VALUES(?,?)", (owner, "Owner"))
            if not store.get("subscriptions_migrated:v1"):
                for topic in TOPICS:
                    store.db.execute(
                        "INSERT OR IGNORE INTO product_subscriptions VALUES(?,?,1)", (owner, topic)
                    )
                for row in store.rows("SELECT * FROM housing_members"):
                    self.enroll(row["user_id"], row["username"], legacy=True)
                store.db.execute(
                    "INSERT OR REPLACE INTO meta(key,value) VALUES('subscriptions_migrated:v1','1')"
                )

            for topic in ("market.outdoor", "market.keyboards"):
                if not store.get("subscriptions_added:" + topic):
                    store.db.execute(
                        "INSERT OR IGNORE INTO product_subscriptions VALUES(?,?,1)", (owner, topic)
                    )
                    store.db.execute(
                        "INSERT OR REPLACE INTO meta VALUES(?, '1')", ("subscriptions_added:" + topic,)
                    )

    def enroll(self, user_id, label, legacy=False):
        self.store.db.execute("INSERT OR IGNORE INTO product_users VALUES(?,?)", (user_id, label))
        self.store.db.execute(
            "INSERT OR IGNORE INTO product_subscriptions VALUES(?,?,?)", (user_id, "housing", int(legacy))
        )
        if not legacy:
            self.store.db.execute(
                "INSERT OR IGNORE INTO subscription_pending VALUES(?,?)", (user_id, "housing")
            )

    def allowed(self, user_id, topic):
        row = self.store.one(
            "SELECT enabled FROM product_subscriptions WHERE user_id=? AND topic=?", (user_id, topic)
        )
        return bool(row and row["enabled"])

    def _watermarks(self, user_id, topic):
        for row in self.store.rows("SELECT source,MAX(event_id) AS id FROM feed_notices GROUP BY source"):
            self.store.db.execute(
                "INSERT OR REPLACE INTO subscription_watermarks VALUES(?,?,?,?)",
                (user_id, topic, row["source"], row["id"]),
            )

    def alerts_enabled(self, user_id, topic):
        return not self.store.one("SELECT 1 FROM muted_alerts WHERE user_id=? AND topic=?", (user_id, topic))

    def set_alerts(self, user_id, topic, enabled, heads=None):
        if not self.allowed(user_id, topic):
            raise PermissionError("Subscription required")
        with self.store.db:
            if enabled:
                self._save_heads(user_id, topic, heads)
                self.store.db.execute(
                    "DELETE FROM muted_alerts WHERE user_id=? AND topic=?", (user_id, topic)
                )
            else:
                self.store.db.execute("INSERT OR IGNORE INTO muted_alerts VALUES(?,?)", (user_id, topic))

    def _save_heads(self, user_id, topic, heads):
        for source, event_id in (heads or {}).items():
            self.store.db.execute(
                """
                INSERT INTO subscription_watermarks VALUES(?,?,?,?)
                ON CONFLICT(user_id,topic,source) DO UPDATE
                SET event_id=MAX(subscription_watermarks.event_id, excluded.event_id)
                """,
                (user_id, topic, source, event_id),
            )

    def set(self, actor, user_id, topic, enabled, heads=None):
        if actor != self.owner:
            raise PermissionError("Owner required")
        if (
            topic not in TOPICS
            or type(enabled) is not bool
            or not self.store.one("SELECT 1 FROM product_users WHERE user_id=?", (user_id,))
        ):
            raise ValueError("Unknown subscription")
        with self.store.db:
            if enabled and not self.allowed(user_id, topic):
                self._watermarks(user_id, topic)
                self._save_heads(user_id, topic, heads)
            self.store.db.execute(
                "INSERT OR REPLACE INTO product_subscriptions VALUES(?,?,?)", (user_id, topic, int(enabled))
            )
            self.store.db.execute(
                "DELETE FROM subscription_pending WHERE user_id=? AND topic=?", (user_id, topic)
            )

    def recipients(self, topic, source, event_id):
        return [
            row["user_id"]
            for row in self.store.rows(
                """
            SELECT s.user_id FROM product_subscriptions s
            LEFT JOIN subscription_watermarks w ON w.user_id=s.user_id AND w.topic=s.topic AND w.source=?
            WHERE s.topic=? AND s.enabled=1 AND ? > COALESCE(w.event_id,0)
            AND NOT EXISTS (SELECT 1 FROM muted_alerts m WHERE m.user_id=s.user_id AND m.topic=s.topic)
            ORDER BY s.user_id
        """,
                (source, topic, event_id),
            )
        ]
