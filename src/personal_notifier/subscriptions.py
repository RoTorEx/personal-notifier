"""Product topic permissions and per-source subscription watermarks."""

TOPICS = {
    "housing": "🏠 Housing",
    "market.astronomy": "🔭 Astronomy",
    "market.digital_pianos": "🎹 Digital pianos",
    "home.temperature": "🌡 Home temperature",
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
            CREATE TABLE IF NOT EXISTS subscription_watermarks(
                user_id INTEGER NOT NULL,topic TEXT NOT NULL,source TEXT NOT NULL,event_id INTEGER NOT NULL,
                PRIMARY KEY(user_id,topic,source));
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

    def enroll(self, user_id, label, legacy=False):
        self.store.db.execute("INSERT OR IGNORE INTO product_users VALUES(?,?)", (user_id, label))
        self.store.db.execute(
            "INSERT OR IGNORE INTO product_subscriptions VALUES(?,?,1)", (user_id, "housing")
        )
        if not legacy:
            self._watermarks(user_id, "housing")

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

    def set(self, actor, user_id, topic, enabled):
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
            self.store.db.execute(
                "INSERT OR REPLACE INTO product_subscriptions VALUES(?,?,?)", (user_id, topic, int(enabled))
            )

    def recipients(self, topic, source, event_id):
        return [
            row["user_id"]
            for row in self.store.rows(
                """
            SELECT s.user_id FROM product_subscriptions s
            LEFT JOIN subscription_watermarks w ON w.user_id=s.user_id AND w.topic=s.topic AND w.source=?
            WHERE s.topic=? AND s.enabled=1 AND ? > COALESCE(w.event_id,0)
            ORDER BY s.user_id
        """,
                (source, topic, event_id),
            )
        ]
