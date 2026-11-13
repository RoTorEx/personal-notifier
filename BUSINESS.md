# Personal Notifier

## Purpose and ownership

One private Telegram notification feed for the owner: Vibecoding now, housing now,
and future independent personal/business sources. Node Radar retains infrastructure
monitoring. Housing collection and its database belong to Housing Watch. Vibecoding
Core owns native execution, sessions and its existing event API. This repository
owns source cursors, the durable delivery queue, pacing and Telegram identity.

## Outbound-only boundary

The production entrypoint only pulls source events and sends notifications. It does
not call getUpdates, accept commands, reply to messages, register callbacks, display
buttons, run agent input, download incoming files or expose an inbound HTTP server.
Links are plain text in messages. No startup notice is sent. Startup removes old
advertised slash commands. The bot token stays solely with this service, pinned to
the existing verified bot username and numeric private recipient.

The Core client still rejects every mutation route and every request body before
transport. Only /health, /sessions, /live and /events?after=<cursor> are allowed.
No provider token, host home, agent database or Docker socket is mounted. Legacy
interactive code/state remains for historical recovery tests but is not imported
by the production entrypoint and cannot be reactivated through Telegram.

## Sources and persistence

Core is the existing built-in source. Its terminal outcomes and questions preserve
session metadata, duration and input counters without forwarding prompts/answers.
Session links lead to the private web workspace and require its existing access.
The original notifier_notices receipts, notifier_cursor and work metadata remain
in bot.db, so migration neither replays history nor loses known successful sends.
Initial Core activation establishes a historical baseline rather than notifying
retained outcomes. Source success timestamps are distinct from process liveness.

Additional [[sources]] use a version-1, read-only Unix HTTP /events endpoint. Each
source has its own cursor and (source,event_id) queue key. Event validation and
queue/cursor persistence happen together in one SQLite transaction, without await.
Vibecoding is a reserved source name. One blocked source cannot block another source
or pending delivery: each has its own asynchronous loop and bounded requests.

The event envelope contains version, events and next_cursor; events carry integer
id, type, title, text, HTTPS url, priority and source-created timestamp when supplied.
IDs increase within a source. next_cursor equals the last returned event, or the
requested cursor for an empty page. There are no producer acknowledgements: source
logs remain available while the notifier owns its durable positions and receipts.
No automatic event pruning is introduced that could skip an offline consumer.

Delivery merges up to ten queued messages per pass by priority/time. Priorities are
0 (ordinary), 1 (time-sensitive work), 2 (urgent candidate). Core keeps priority 1.
Housing priority 2 is a lead requiring verification, not proof of price or location.
The existing shared 1.05-second write pacer remains. Telegram success records its
message ID; known successful sends do not repeat on restart. A lost acceptance
response or crash before recording may repeat a send: exactly-once is not claimed.

## Runtime and decisions

Own Compose project and /srv/personal-notifier/{runtime,config,data}. SQLite stays
on durable host disk. Token is a mode-0600 file. No shared producer database.
Core is polled every three seconds as before; generic sources default to fifteen
seconds, configurable per source. Delivery checks once per second. These intervals
are responsiveness defaults, not publication-latency guarantees. The owner requested
Housing Watch collection every 600 seconds, separately from this feed polling.
Health checks validate current process instance/PID and delivery-loop heartbeat
within 120 seconds; source failures remain separate from process readiness.

The independent container has a 256 MiB memory ceiling and 0.25 CPU as initial
bounds for this small single-user process; observe runtime before tuning. Source
and transport messages are untrusted data and cannot become instructions.

## Source map and migration

notifier.py: built-in Core adapter, durable capture and independent loops.
feeds.py: bounded generic pull protocol validation and client.
config.py: explicit TOML settings. cli.py: outbound-only entrypoint and liveness.
store.py/pacing.py: existing SQLite and Telegram pacing contracts.
compose.yaml/Dockerfile: independent runtime. docs/OPERATIONS.md: cutover/recovery.
Historical changelog entries describe the earlier name and deployment.
