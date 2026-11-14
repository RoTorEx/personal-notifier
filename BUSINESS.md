# Personal Notifier

One private Telegram notification feed for the configured numeric owner, with
explicitly invited housing-only participants. Independent
sources own their data: Housing Watch owns collection, cards, queue membership and
viewed/favorite flags; Vibecoding Core owns native sessions and execution. This
repository owns Telegram identity, event cursors, delivery receipts and review UI.
Node Radar retains infrastructure notifications. No source implementation is imported.

## Home deck and owner boundary

The English Home deck contains Vibecoding and Housing. Vibecoding shows only an
Under construction callback alert; its existing independent push notices continue.
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
Carousel buttons edit the existing message. Telegram cannot remove photo media
through an edit: returning to a text menu or empty screen sends the genuine text
screen and removes the previous photo message. Never fabricate a placeholder image.
Initial commands may create a screen. Explicit photo rejection falls back to text;
ambiguous transport failures propagate. Every successful screen retains a nonempty
keyboard in Telegram's returned Message; repair missing markup and read it back.
API markup confirms server state but not physical client rendering.

## Quiet notifications and persistence

Housing Watch scans every 600 seconds on ten-minute wall-clock boundaries and owns digest/reminder timing. Queue-mode
capture advances past legacy individual housing.listing.* events without pushing
them. Only *.queue.summary and *.queue.reminder enter delivery. New findings produce
one Housing alert count with View queue. Both owners and participants re-read the
current personal unviewed count immediately before sending every alert/reminder;
producer event text is a historical snapshot and must never supply that number.
For every new-finding alert, pass the source event ID to /queue and replace both
new and remaining counts from that atomic response. Suppress it when new_total=0,
even with old unviewed apartments remaining. Never infer freshness from a scan's
text or total. Retain event_type during capture; legacy alert headings remain
recognized. A personal empty queue or no live digest members skips the event
durably in housing_skips, without fake
Telegram receipts or blocking another recipient. Counts describe the queue at send
time; an old notification is not a continuously updating counter. Zero-found scans are silent. A nonempty
queue may produce Housing reminder after 3,600 seconds since the previous notice;
empty queues never remind. Send reminders only from 12:00 inclusive until 00:00
exclusive in Europe/Warsaw, using the event date's CET/CEST offset. New-finding
alerts remain unrestricted. The sender checks the actual delivery window even for
previously queued producer reminders: mark excluded notices suppressed, retaining
history without fabricating a Telegram receipt or replaying a backlog at noon.
Each invited participant has an independent hourly
reminder clock and personal queue count; owner producer reminders do not fan out. Browsing uses current old-plus-new unviewed entries.
Pure source updates refresh cards without creating new-identity notifications.

Generic non-queue feeds retain their existing text/photo notifications. Vibecoding
keeps its distinct [Vibecoding] outcome notices. Source captures and cursors commit
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
