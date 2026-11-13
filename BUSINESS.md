# Personal Notifier

One private Telegram notification feed for the configured numeric owner. Independent
sources own their data: Housing Watch owns collection, cards, queue membership and
viewed/favorite flags; Vibecoding Core owns native sessions and execution. This
repository owns Telegram identity, event cursors, delivery receipts and review UI.
Node Radar retains infrastructure notifications. No source implementation is imported.

## Home deck and owner boundary

The English Home deck contains Vibecoding and Housing. Vibecoding shows only an
Under construction callback alert; its existing independent push notices continue.
Housing opens the unviewed queue, newest discovery first. Favorites is an operation
inside Housing. Carousel arrows change the current item within one screen. The
separate final navigation row contains Back (previous screen) and the compact
🏠 Deck exit, matching the Telegram Assist navigation convention. Favorites Back
returns to the housing queue; Housing Back returns to the deck. Empty states keep
Back/Deck. Operations and source/contact links always precede navigation.

Only allowed_user_id in its matching private chat can open screens or mutate source
state. Check both sender ID and chat before any source request or Telegram response;
ignore other users, groups and unrelated input. All outgoing messages/edits target
that same configured ID. Telegram commands are advertised only in that owner's chat.
The startup identity check remains pinned to the existing bot username/token.

A small independent getUpdates loop handles only deck commands and the registered
review callbacks. It never dispatches to historical BotRuntime, agent input,
execution approval, enrollment, uploads or provider settings. CoreClient remains
strictly read-only: /health, /sessions, /live and /events?after=. Incoming text or
source data can never become instructions or execution. No Docker socket, producer
DB, host home or provider token is mounted.

## Housing queue interaction

Queue-capable sources explicitly opt into queue=true in TOML. FeedClient uses GET
/queue and narrowly scoped PATCH /items/{connector}/{id} on that source's Unix socket;
only absolute viewed/favorite booleans are accepted. No direct producer DB writes.
A separate source queue capability cannot enable mutations against Vibecoding Core.

Cards show type, publication/update dates, seller, price, location, property details,
short description and main photo. Source-owned HTML escapes untrusted values and
fits Telegram's 1,024 UTF-16-unit caption budget. Keep the metadata above the photo.
The first row is Viewed/Favorite. Then Favorites (or View queue), followed by source
buttons named OLX/Otodom and native Copy phone when publicly available. Carousel
arrows and Back/Deck remain distinct navigation rows at the bottom.

Viewed hides a listing without deleting it. Favorite is independent; favorites can
include viewed items and offer Unview. Review views persist opaque tokens tied to
the shown source item and Telegram message ID. Repeated stale callbacks cannot
toggle another item. State writes are absolute/idempotent; restart keeps the view
and source-owned flags. Explicit photo rejection falls back to formatted text;
network ambiguity retains normal retry semantics. Telegram cannot remove a photo
in place, so photo-to-text transitions send a replacement then remove the old card.

## Quiet notifications and persistence

Housing Watch scans every 300 seconds and owns digest/reminder timing. Queue-mode
capture advances past legacy individual housing.listing.* events without pushing
them. Only *.queue.summary and *.queue.reminder enter delivery. New findings produce
one Housing alert count with View queue. Zero-found scans are silent. A nonempty
queue may produce Housing reminder after 1,800 seconds since the previous notice;
empty queues never remind. Browsing uses current old-plus-new unviewed entries.
Pure source updates refresh cards without creating new-identity notifications.

Generic non-queue feeds retain their existing text/photo notifications. Vibecoding
keeps its distinct [Vibecoding] outcome notices. Source captures and cursors commit
atomically; known successful Telegram message IDs never replay on restart. A lost
acceptance response or crash before receipt may repeat a send: exactly-once is not
claimed. Producer logs have no consumer acknowledgements or automatic pruning.

Each source, Core collection, owner polling and delivery has an independent async
loop, bounded HTTP requests and durable offsets. A slow source cannot block others.
Core polls every three seconds, feeds every fifteen seconds, delivery every second.
The shared 1.05-second Telegram write pacer covers sends and edits. Source liveness
is distinct from process health, which checks this PID/instance and a 120-second
heartbeat. Runtime remains a separate Compose project under /srv/personal-notifier,
with 256 MiB / 0.25 CPU initial bounds and a mode-0600 token file.

## Verification and operations

Run make check, including owner/group rejection, deck versus carousel navigation,
flags, stale callbacks, summary-only delivery, photo fallback and state migration.
Verify the actual configured recipient, source socket reads, Telegram acceptance and
installed revision on the VPS. Do not claim physical clipboard behavior or a user's
reading from a successful send. See docs/OPERATIONS.md for updates and recovery.
Preserve source cursors, session identity, queue rows and existing Telegram receipts.
