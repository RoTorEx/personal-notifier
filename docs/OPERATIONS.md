# Personal Notifier operations

Production is the independent personal-notifier Compose project under
/srv/personal-notifier. Read private config/bot.toml at startup, obtain the token
from its protected file, and verify the existing numeric bot identity and owner.
Never print secrets or substitute another bot's credentials.

Web Watch owns Housing/Market observations and per-user review flags. Mount only
its run directory read-only at /run/web-watch and read/PATCH the private Unix API;
never mount its database. Node Tools supplies /api/v1/climate through its read-only
socket. Home rules and product subscriptions remain owned by Notifier's bot.db.

Technical Vibecoding outcomes belong to Node Tools → Node Radar. Production sets
core_enabled=false and has no Core socket mount. That flag gates both collection
and unsent legacy Core rows. Keep original cursor/work/receipt tables intact.
Do not reenable old Core delivery without reconciling Radar receipts, because a
Telegram acceptance followed by a lost acknowledgement can cause a duplicate.
Old Vibecoding callbacks/commands explain the new technical bot location.

Run make check before a release. Use interactive make release, then make
release-push. Build the exact tagged image separately, snapshot bot.db and private
configuration while the single notifier is stopped, update only its image/config,
then start it and verify health, topic permissions and actual source API reads.
Do not start a second live Telegram poller during verification. Verify full-handler
flows in a separate bounded container with isolated data and a fake Telegram
transport, retaining the real source/socket only for read-only live checks.

Keep 256 MiB / 0.25 CPU limits and the existing socket group. Native Web Watch and
Node Tools are independent applications. Do not restart Core, sensor collectors,
backup/calendar jobs, or unrelated bots during a Notifier rollout.

Recovery snapshots remain under each application's recovery directory, with exact
locations in its runtime/deployment.json and project verification record. Retain
until a later verified deployment explicitly retires them. Database restoration
requires cursor and delivery-receipt reconciliation; restoring a file alone is
not a safe rollback procedure. Activity goes to the existing container journal;
never log listing descriptions, public phone numbers, tokens or incoming text.

## Missing product notifications

Compare source last-success timestamps and actual queue/event membership with
feed_cursor:<source>, feed_notices and housing_receipts. Repeated ValueError at
a fixed cursor can be a producer/consumer contract mismatch, including optional
presentation fields. Exercise the installed FeedClient, not only an unvalidated
HTTP GET or a stubbed ReviewUI. Distinguish a validated source read, a captured
notice and a real Telegram receipt. Preserve review state and subscriptions.

For a verified delivery outage, recover genuinely unviewed post-reset identities
through one source-owned catch-up digest per topic. Supersede undelivered old
summaries only after protected snapshots and receipt reconciliation. Never invent
Telegram IDs, reset favorites or replay every historical alert as a test.
