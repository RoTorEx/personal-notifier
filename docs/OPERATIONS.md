# Operations

Production is an independent Compose project in /srv/personal-notifier/runtime.
Configuration/token are in /srv/personal-notifier/config and bot.db in its data
folder. Mount only the existing Core socket directory and Housing Watch socket
directory read-only. The deployment UID/GID is the existing alex identity, 1002.

For first cutover, build and test the released image before stopping the old
remote-vibecoding bot service. Save the old installed Compose/ops files, stop only
that old bot, and take a consistent SQLite backup into the new data directory.
Reconcile table counts and known delivery receipts. Copy its token without printing
it; preserve the verified username and numeric recipient. Start the new service,
read back version/capabilities/health, and check both source success timestamps.
Core container ID and active native sessions must remain unchanged. Never run two
senders against different copies of the same queue. Keep old state and image for
rollback, but remove the old service from normal Core startup.

The active bot display name is Personal Notifier. Telegram usernames are separate
identities and may require BotFather to rename; do not invent a new handle or token.
The existing pinned handle and chat are retained when only the display name changes.

Updates build the reviewed Git revision as personal-notifier:<version>, then run
`docker compose -f /srv/personal-notifier/runtime/compose.yaml up -d` with the
matching VERSION. This replaces only Personal Notifier. It must not restart Core,
Housing Watch or Node Radar. A rollback stops the current sender first and restores
one known notifier/state combination; never replay pending queues blindly after
ambiguous Telegram acceptance. Verify actual Telegram history before repair.

make release is interactive; make release-push publishes the reviewed branch/tag.
Source publication does not itself deploy. For 0.1.32 and later, housing opts
into queue=true in its source block. The bot long-polls only owner deck/review
interactions; command scope is the pinned private owner's chat. Verify Home deck,
Vibecoding alert, queue/favorites, Back/Deck, sender/chat rejection and the producer
review API without enabling any Core mutation path. Preserve session IDs, source cursors,
known Telegram message IDs and token files outside Git. No secrets in command text.

## Verified 13 November 2026 cutover

Personal Notifier 0.1.31 runs in its own healthy Docker container. The former
remote-vibecoding bot container was removed only after health and unchanged Core
identity were verified. Telegram display name/description were updated and its
advertised command list is empty. The existing Telegram handle/token/recipient are
retained; a handle change is a separate BotFather operation, not setMyName.

Housing Watch uses native systemd on the same VPS because that exact source client
worked natively while the container source preflight returned 403. Both producer
socket directories remain read-only mounts in the notifier. Source success keys
and feed_cursor:housing prove independent capture; feed_notices.telegram_id records
Telegram acceptance. These receipts do not prove the operator has read a message.

After a root-run SQLite backup or verification, ensure every bot.db, bot.db-wal and
bot.db-shm file has the service UID/GID before starting the unprivileged notifier.
Checking only the main file left root-owned WAL/SHM files and prevented startup in
the first cutover attempt. No files were deleted to recover. Old state/image and
installed-operator backups remain under the prior room and config/migration.
A rollback after new sends must reconcile the current queue/receipts before any
old process is reactivated; restoring an older queue blindly can resend messages.

## Housing participants and logs

Configure housing_usernames outside Git. Each invited user must privately send
/start after the supporting release is installed; Bot API cannot resolve arbitrary
private usernames or initiate a conversation before Start. Read back housing_members
to verify numeric enrollment, then housing_receipts and housing_guide:v1:<id> for
Telegram acceptance. Never report a recipient as enrolled from configuration alone.
The owner retains Vibecoding notices; participants receive housing only.

The producer owns actor-scoped review_actors. Deploy both sides before enabling a
participant; an older producer ignores unknown actor queries. Reconcile source
eligibility using the updated search config while preserving existing flags.
Personal Notifier preserves legacy review_views and migrates owner screens into
chat-scoped review_screens. Keep backups before either additive migration.
Read activity through docker logs personal-notifier and journalctl -u housing-watch;
existing journald retention applies. No extra file log or unbounded duplicate sink.
