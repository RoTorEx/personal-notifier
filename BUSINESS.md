# Personal Notifier

One private Telegram notification feed for the configured numeric owner, with
explicitly invited housing-only participants. Independent
sources own their data: Web Watch owns collection, cards, queue membership and
viewed/favorite flags; Vibecoding Core owns native sessions and execution. This
repository owns Telegram identity, event cursors, delivery receipts and review UI.
Node Radar retains infrastructure notifications. No source implementation is imported.

## Home deck and owner boundary

The English Home deck contains subscribed Housing, Market and optional Home connections, plus owner-only Settings. Vibecoding outcomes belong to Node Radar; retained old commands/callbacks point there. No execution or technical collection entry appears in the product deck.
Housing opens a text section menu with 📋 Queue and ⭐ Favorites. Each collection
has its own carousel. Viewed removes a card from Queue immediately. Removing a
favorite inside Favorites keeps that card visible and undoable until explicit
navigation or leaving the collection, including across a notifier restart.
The card's first keyboard row combines Viewed, ☆/★ Favorite and the source link.
An optional phone copy row follows. Emoji carousel arrows occupy the next level;
Back returns to Housing, while the final 🏠 Deck exit returns to the Home deck.
No collection switch button or counter button appears inside the carousel.
Empty states retain Back/Deck. Home entries include emoji.

The numeric allowed_user_id retains all original notices. housing_usernames
explicitly invites housing-only users: the first private /start from the exact
Telegram username pins its numeric ID in durable housing_members. An existing
binding never transfers to a replacement username holder. Both sender and private
chat ID must match before reads, writes or replies. Unlisted users and groups are
ignored. Housing participants receive only housing notices, never Core outcomes.
Commands remain advertised only in the owner's chat; participants can use /start,
/menu, /housing and the same inline controls.

A small independent getUpdates loop handles only deck commands and the registered
review callbacks. It never dispatches to historical BotRuntime, agent input,
execution approval, legacy enrollment, uploads or provider settings. CoreClient remains
strictly read-only: /health, /sessions, /live and /events?after=. Incoming text or
source data can never become instructions or execution. No Docker socket, producer
DB, host home or provider token is mounted.

## Housing queue interaction

Queue-capable sources explicitly opt into queue=true in TOML. FeedClient uses GET
/queue and narrowly scoped PATCH /items/{connector}/{id} on that source's Unix socket;
only absolute viewed/favorite booleans are accepted. Guests pass an opaque actor
identity; the empty legacy actor keeps the owner's existing review flags unchanged. No direct producer DB writes.
A separate source queue capability cannot enable mutations against Vibecoding Core.
Mark all viewed appears in a nonempty Queue. It issues one PATCH /queue with
`{"viewed":true}` for the current topic and actor. The producer atomically marks
the currently eligible unviewed items and returns a count. Favorites, other
queues and users, and items arriving after the operation retain their state.
Invalidate previews and earlier cards for the affected collection and user so
replaying the same button cannot clear later arrivals. An unconfirmed result
offers a fresh queue read.

Cards use source-owned seller, Published and Updated on separate bold lines,
price, location/street, property facts, explicit amenities and available description/
contact. Preserve apartment photos with the standard photo-first layout. A separated
technical footer shows Queue/Favorites position and Last refresh in Europe/Warsaw.
Refresh means the oldest latest successful fetch across the producer's searches,
not publication time or the bot's polling time. Captions fit 1,024 UTF-16 units.
Only push summaries repeat the Housing alert type, not every browsed card.

Viewed hides a listing without deleting it. Favorites can include viewed items and
offer Unview. Review views persist opaque tokens tied to source item and Telegram
message ID. Repeated stale callbacks cannot toggle another item. Writes are
absolute/idempotent; restart keeps source flags and the current undoable card.
One combined area feed has per-person Viewed/Favorites. Tokens are scoped to
(chat_id, message_id), since private chats can reuse message IDs. The additive
review_screens migration retains the owner's live tokens and leaves legacy rows.
↕️ Sort cycles Published (source publication descending across all platforms), Updated (source refresh descending)
and Rent (advertised PLN ascending, unknown prices last), persists per collection/
person, and resets to the first card when changed. Opening Queue from a digest,
Housing or /queue explicitly starts in Published order, irrespective of a prior
price sort. Explicit carousel sort changes still persist while navigating.
While publishing a Queue or Favorites card, fetch the next two available cards
in the background so forward navigation can reuse their source data. Keep one
lookahead window per recipient, tied to the active card's token and current sort.
Previews expire after 15 seconds to limit stale ordering and flags after source
updates. Reopening or sorting a collection and changing review flags discard the
previous window. Mutations and notification counts continue to use the live
source. Missing or failed previews fall back to live reads. Button acknowledgements
run concurrently with rendering. Telegram still controls media loading and the
existing write pace applies to message edits.
Carousel buttons edit the existing message. Telegram cannot remove photo media
through an edit: returning to a text menu or empty screen sends the genuine text
screen and removes the previous photo message. Never fabricate a placeholder image.
Initial commands may create a screen. Explicit photo rejection falls back to text;
ambiguous transport failures propagate. Every successful screen retains a nonempty
keyboard in Telegram's returned Message; repair missing markup and read it back.
API markup confirms server state but not physical client rendering.

## Quiet notifications and persistence

Web Watch scans every 600 seconds on ten-minute wall-clock boundaries and owns digest timing. Queue-mode
capture advances past legacy individual housing.listing.* events without pushing
them. Only *.queue.summary enters delivery; legacy *.queue.reminder events advance
the cursor without being captured. New findings produce
one Housing alert count with View queue. Both owners and participants re-read the
current personal unviewed count immediately before sending each new alert;
producer event text is a historical snapshot and must never supply that number.
For every new-finding alert, pass the source event ID to /queue and replace both
new and remaining counts from that atomic response. Suppress it when new_total=0,
even with old unviewed apartments remaining. Never infer freshness from a scan's
text or total. Retain event_type during capture; legacy alert headings remain
recognized. A personal empty queue or no live digest members skips the event
durably in housing_skips, without fake
Telegram receipts or blocking another recipient. Counts describe the queue at send
time; an old notification is not a continuously updating counter. Zero-found scans are silent. Existing queue entries never trigger automatic
reminders, at any time of day, for either the owner or participants. Reminder
capture and guest generation are retired. Suppress already-pending reminders by
type or legacy heading without generating fake delivery receipts or altering the
queue. Direct menu/queue interactions and the requested once-only guide remain
available. Browsing uses current old-plus-new unviewed entries.
Pure source updates refresh cards without creating new-identity notifications.

Generic non-queue feeds retain their existing text/photo notifications. Vibecoding
outcomes are read by Node Tools and delivered by Node Radar. Production sets
core_enabled=false; both Core collection and pending legacy delivery are disabled.
Keep the old cursor, work counters and genuine receipts for handover/recovery,
without a Core socket mount in the product bot. Source captures and cursors commit
atomically; known successful Telegram message IDs never replay on restart. A lost
acceptance response or crash before receipt may repeat a send: exactly-once is not
claimed. Producer logs have no consumer acknowledgements or automatic pruning.
Housing delivery records one receipt per source event/recipient. A partial failure
retries only missing recipients; enrollment starts at the current event watermark
rather than replaying historical alerts. Apartment-only membership is source-owned. Startup and a participant's first /start
send one durable Quick guide with a View queue button per person. This guide is an
explicitly requested one-time release notice, not a recurring reminder.

Each source, Core collection, owner polling and delivery has an independent async
loop, bounded HTTP requests and durable offsets. A slow source cannot block others.
Core polls every three seconds; the housing feed polls every 900 seconds on
quarter-hour clock boundaries, without a startup burst or offset. Generic feeds keep
their configured interval. Delivery runs every second, while owner buttons remain
immediate and independent of scheduled feed capture.
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

Activity logs use the existing container journal: feed polls/cursors, successful or
failed deliveries with numeric recipient/event IDs, enrollment and guide receipts.
The producer journal records source/scan lifecycle and successful review mutations.
Never log bot tokens, phone numbers, listing descriptions or incoming message text.

## Product subscriptions

Personal Notifier owns product_users, product_subscriptions and per-source
subscription_watermarks. Stable topics are housing, market.astronomy,
market.digital_pianos, home.temperature, market.outdoor and market.keyboards. Housing, Market and optional Home climate connections are supported; the
Vibecoding-to-Radar handover preserves the prior cursor, work counters, pending
outcome identities and genuine receipts in a protected one-off export.
Existing pinned members migrate to Housing only. The owner starts subscribed to
all supported topics; startup never overrides later subscription changes.
Settings presents Topics → subscribers and Users → subscriptions, as two views
of the same persisted relation. Only the numeric owner can inspect or change it.
Existing username-based invitations remain the enrollment mechanism in this stage.
A disabled Housing subscription excludes recipients before sending and rejects
source reads/writes and stale carousel callbacks. User identity and existing review
state remain stored. Reenabling reads each connected producer through its current event watermark
without capturing notices or advancing capture cursors. New enrollment remains
pending with Housing disabled until the same read succeeds; a later private
request retries it. Reads have a ten-second overall budget and at most 100 pages
per producer; failure leaves the subscription unchanged. Disconnected future
topics have no producers yet. Settings remains accessible to the owner even
when every review subscription is disabled.

Settings → Notifications toggles the owner's pushes per connected topic.
Muting is persistent and independent of collection access, review flags and
other recipients. Resuming starts after the latest event watermark from each
producer, including the local Home alert outbox. If a producer is unavailable,
the topic remains muted. Scans and carousel browsing continue while muted.

## Home: notification-only indoor climate

Home is an optional connection inside Notifier, enabled by home_socket. Node Tools
owns the sensor collector, raw accepted readings and freshness policy. Read its
existing GET /api/v1/climate through the private read socket; never read its DB,
chart means, CPU temperature or repeatedly dated last-valid fallbacks as current.
The source's latest attempt must be successful, synchronized and fresh by both
source/receipt time. Missing/stale data is unavailable, never zero or recovery.

Poll every 600 seconds normally. A new declining temperature or active cold
incident switches to 60 seconds. Two distinct non-declining readings >=15.5 Celsius
restore normal polling and rearm the incident. A duplicate never counts twice.
The first cold signal is strictly below 15; subsequent 0.5-degree boundaries
(14.5,14,13.5,...) include equality and notify once per incident. A large jump
produces one current alarm. Additionally send Temperature alarm every 300 seconds
while fresh temperature is below 15, regardless of movement. The first cold alarm
starts this cadence; intervening threshold crossings do not postpone it, and
coincident triggers coalesce. >=15 stops repeats; recovery is quiet. All alarms
are available around the clock only to home.temperature subscribers.

State, cadence and an outbox survive restart. Reconcile current fresh temperature
rather than replay missed timers; stale/warm observations supersede pending cold
warnings. Retry independently per recipient and retain actual sent readings in
receipts. Say decreased only against that recipient's last reported temperature;
otherwise say remains below threshold. Home has no Viewed/Favorites/queue actions.
Its screen shows temperature, source measurement time, freshness and episode state.
Only the owner is subscribed initially; housing members retain their existing
scope. Technical collection/availability policy stays with Node Tools/Radar.
Normal polling may detect the first drop up to ten minutes late and miss dips
between observations. The sensor's own cadence bounds new measurement frequency.

## Interactive product connections

Web Watch provides Housing, Astronomy, Digital pianos, Outdoor and Keyboards through one private API
and database. Each configured queue source selects its explicit product topic;
missing topic retains legacy Housing compatibility. Check this topic in producer
responses before admitting data, and read it again before product mutations so
an older producer cannot silently treat a Market action as a Housing action.
Feed cursors, subscriptions and recipient receipts remain source-specific.

Home deck → Market → Astronomy/Digital pianos/Outdoor/Keyboards → Queue/Favorites uses exactly the
Housing collection interaction: same photos, Viewed, favorite undo, source link,
public phone copy, Published/Updated/base-price sort, carousel and Back/Deck.
Market sections inherit the subscribed topic, never another user's permissions.
Home temperature is notification-only and offers no object queue mutations.
Bounded JSON reads consume the full HTTP body before parsing, including chunked
Node Tools responses, while retaining the request deadline and total size limit.

## Outdoor subscription and interface

Outdoor is another Market collection using exactly the same source-owned review
UI and API boundaries as Housing/Astronomy/Pianos. Its producer watchlist is owned
by Web Watch business/outdoor.md. New existing installations enroll only the owner
once; invited housing participants retain their scope. Respect an owner's later
opt-out on restart. Append the new topic after existing topics to preserve numeric
management callback identities. Photo cards, source links, Viewed, undoable
favorite, sort, carousel and Back/Deck reuse the existing implementation.

## Single-message photo galleries

Review cards use one Telegram rich message with a slideshow of up to ten distinct
source photos, the existing description/technical footer and inline controls.
Edit that same message while moving through the queue, sorting or changing flags.
A single-photo listing keeps the single-photo layout; when already in a rich
card, retain its message identity for a one-photo successor. Menus remain text.
An explicit gallery rejection falls back to one photo; ambiguous network failures
are not retried as another send. No automatic separate albums or Photos button.
The capability uses aiogram's installed typed Bot API rich-message support.

## Producer contract and notification delivery verification

The consumer validates optional photo_urls as a JSON list of at most ten unique
HTTPS image URLs, alongside the legacy photo_url. The same presentation contract
applies to event pages and queue cards. A valid gallery must not prevent cursor
progress; invalid input must not advance it. Queue consumers request
/events?queue_only=1 to read summaries without a backlog of listing updates. An
older producer may ignore this additive filter, so mixed pages remain supported.

A sender or UI test using a stubbed queue does not verify this boundary. Exercise
the real FeedClient over Unix HTTP through capture, notice validation, a genuine
transport receipt and gallery browsing; retain no-repeat behavior on restart.
Production verification must observe source event, consumer cursor, notice and
recipient receipt, rather than infer delivery from running processes or GET 200.

Telegram access denials retain the undelivered recipient and retry the notice
after 3,600 seconds. Persist this retry_at deadline, select only due rows before
the delivery batch limit, and preserve successful recipients' receipts. This
prevents a blocked participant from producing a per-second retry loop or starving
new owner notices. A different transient error retains the existing retry path;
subscriptions are never silently disabled and no acceptance receipt is invented.

## Keyboard connection

Market → ⌨️ Keyboards → Queue/Favorites reuses the same review UI, gallery,
Viewed, favorite undo, sort, source link and Back/Deck transitions. Web Watch owns
the nationwide Lofree watchlist and advisory targets in business/keyboards.md.
Enroll the owner once; preserve later opt-out and every other subscription.
Housing guests are not enrolled in Keyboards. Append its management topic after
all existing topics to keep persisted callback indices stable.
