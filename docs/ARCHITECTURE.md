# Product and technical notification architecture

| Owner | Input | Output / capability |
| --- | --- | --- |
| Web Watch | Public listing platforms | Topic-partitioned observations, review flags and private Unix queue/event/PATCH API |
| Personal Notifier | Web Watch, Node Tools climate | Product subscriptions, interactive Housing/Market collections and notification-only Home alarms |
| Node Tools | Telemetry and GET-only Core outcomes | Durable technical pending/history/ack contract |
| Node Radar | Node Tools private read API | Technical delivery to the existing sole numeric operator, send before ack |

Applications retain independent repositories and writable databases. Housing and
Listing are modules of Web Watch; Home rules are inside Notifier. No shared
writable database, separate Home service, broker or per-topic Telegram bot exists.
Product review state is per person and topic. New listings notify; old queues and
pure updates do not. Node Radar owns technical outcomes independently of product
subscriptions. Ira remains Housing-only unless explicitly changed by the owner.

## Verified technical cutover

Node Tools 0.14.1 already contained the reviewed read-only Vibecoding producer;
its installed source SHA-256 matched the merged source. Radar 0.11.0 was deployed
first. The protected handover imported cursor 3637 and 17 session work states;
there were zero pending outcomes and zero prior Core delivery receipts. The old
Notifier tables remain intact. The producer now reads on its three-second timer
through the existing monitoring database/consumer scope. Only vibecoding was added
to Radar's operations allowlist; node/service policies and disabled Pi alerts were
unchanged. Existing real technical deployment notifications retain genuine ack
receipts. No synthetic outcome was inserted into production.

Notifier 0.5.0 disables both Core collection and legacy pending sends, and its
Compose runtime has no Core socket mount. Old technical controls point to
@node_radar_bot. The Core container ID and start time were unchanged across the
cutover. Both bots and the native receiver/timer were verified healthy/successful.
Radar passed 70 checks; Notifier passed 217 checks, Ruff and mypy. Source capture
was observed without replay; a future real Core outcome exercises the new payload
end-to-end, so no such user-visible delivery is claimed from the quiet cutover.

## Verified Home boundary

An isolated container used the real read-only Node Tools climate socket, isolated
state and a fake Telegram transport. It read a fresh 24.981 Celsius observation
and exercised the Home screen with measured time and Back/Deck controls, without
queue actions or a production alarm. Tests cover the strict 15-degree threshold,
0.5-degree bands, five-minute repeats, duplicate/stale/out-of-order data,
subscription isolation, real database close/reopen and no restart burst. No real
cold-sensor event or physical phone rendering is claimed. A brief source failure
during the receiver restart was followed by fresh successful polls.

## Recovery ownership

- Node Tools: /srv/node-tools/recovery/vibecoding-handover, including protected
  export, monitoring/config snapshot and verification.json.
- Notifier: /srv/personal-notifier/recovery/vibecoding-handover-0.5.0.
- Radar: /srv/telegram-node-radar/recovery/before-vibecoding-0.11.0.

Retain until a later verified rollout explicitly retires these points. Reconcile
both bots' genuine receipts before enabling an old sender or restoring producer
state. A lost Telegram acceptance/ack can repeat a delivery; exactly-once is not
claimed. Never restart Core, trigger backup/calendar jobs, fabricate a climate
reading or reenable disabled monitoring to verify these flows.

## Outdoor rollout

Personal Notifier 0.6.0 and Web Watch 0.3.2 add Market → Outdoor →
Queue/Favorites. The owner-supplied brand requirements explicitly mean Rab and
Stellar Equipment. The complete producer watchlist is owned by Web Watch
business/outdoor.md; unavailable reel content is not represented as inspected.

An isolated bounded container exercised the released ReviewUI against real
source DTOs and a copied BotStore with fake Telegram: Market entry, queue/photo,
favorites, Viewed, favorite removal and undo across restart, Published/Updated/
price sorting, arrows, empty state, Back/Deck and denial to an unsubscribed guest.
The test sent no real Telegram messages and made no production review writes.
The installed owner scope includes Outdoor; Ira retains Housing-only. Local
Notifier checks passed 219 tests, Ruff and mypy. Installed source hashes match.
Initial source inventories are quiet; new identities produce topic-specific
digests, while source updates and old queues remain silent.

The large national scan exposed a producer writer race and queue read latency.
Web Watch 0.3.1 serialized writes and 0.3.2 indexed source date/price ordering;
producer migration verified raw records, original review fields and receipts
were preserved. Web Watch docs/DEPLOYMENT.md owns full-scan/load evidence and
its resource/public-search limitations. Notifier recovery for Outdoor is
/srv/personal-notifier/recovery/outdoor-0.6.0, retained until a later verified
rollout explicitly retires it.

The original local Radar checkout could not fast-forward because its unrelated
uncommitted files would be overwritten. Those edits were preserved; release
0.11.0 was built from the clean merged source. The task-owned clean checkout at
~/construction_side/telegram-node-radar/notifier-release is intentionally retained
as the verified source until the owner reconciles the original local edits and
its upstream. It can then be removed. This does not affect the deployed release.

## Verified single-message galleries and reset

Personal Notifier 0.6.1 is installed with Web Watch 0.3.3. A temporary silent
owner-only Telegram call used seven real source photos in one rich slideshow
message, edited the same message ID, retained inline controls and then deleted
the preview. Review tests cover a ten-photo cap, in-place carousel navigation,
unsubscribed-user denial and explicit rejection falling back to one photo.
All 221 tests, Ruff, mypy and both release CI runs passed. Installed source
hashes match the released source. This verifies API acceptance; no physical
client screenshot is claimed.

The owner confirmed clearing Queue and Favorites for both registered people.
All sixteen live actor/topic/mode views returned zero. Existing source records,
subscriptions, climate state and genuine technical receipts were retained; saved
review screens were invalidated. Producer reset semantics and geographic/source
limitations are owned by Web Watch BUSINESS.md and docs/DEPLOYMENT.md. Eight
Allegro searches remained rate limited in preflight; no successful complete new
inventory is claimed.

Notifier owns /srv/personal-notifier/recovery/gallery-reset-0.6.1 and Web Watch
owns /srv/web-watch/recovery/scope-reset-0.3.3. Retain until a later verified
rollout explicitly retires them; reconcile current identities and receipts
before any restoration. No temporary gallery, database copy or probe process
is needed after verification.
