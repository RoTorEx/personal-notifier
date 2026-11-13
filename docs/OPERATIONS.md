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
Source publication does not itself deploy. Preserve session IDs, source cursors,
known Telegram message IDs and token files outside Git. No secrets in command text.
