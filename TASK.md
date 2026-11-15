# Accepted implementation queue

The owner approved the full product/technical notification plan on 15 November
2026. Work personally, without subagents. Implement and verify each release slice
before publishing/deploying it. English artifacts and UI; preserve credentials,
identities, producer data, per-person flags and real delivery receipts.

## Current checkpoint

- Housing Watch 0.1.11 is published and deployed at revision
  3bd82276b674c61171411e17b7faf44d66dad868. Issue #1's eight-area alias matcher
  and 3,500 PLN inclusive base-rent limit are active. Archive reseeding preserves
  owner/participant flags and event count. Release messages were accepted by
  Telegram for Alex (163) and Ira (164). Recovery belongs to Housing Watch under
  /srv/housing-watch/{runtime,data}/before-areas-0.1.11. Retain until a later
  verified deployment explicitly retires it; reconcile cursors before DB restore.
- Personal Notifier 0.2.0 is published at revision
  0c3d6ef1a3c605422a293717cfd3e51381a1963c and deployed. All 206 tests,
  Ruff, mypy and both GitHub checks pass. The deployed process is healthy;
  real Telegram Management/read-back verification passed (owner deck message 167,
  producer head 134). Numeric pins, real delivery receipts and once-only guide
  receipts are preserved; Ira remains Housing-only. Recovery belongs to Notifier
  under /srv/personal-notifier/{runtime,data}/before-subscriptions-0.2.0. Retain
  until a later verified deployment explicitly retires it; reconcile receipts
  before restoring data.
- The owner subsequently requested a one-off current-queue clear for both users,
  except each person's Favorites. Completed on the VPS: owner 441 → 9 (Favorites),
  Ira 546 → 0. Observations/events and favorite flags are unchanged. Existing
  queue rows are announced and per-recipient Housing watermarks are at event 134,
  so old pending notices cannot replay. Recovery directories under each producer's
  data owner are before-queue-clear-1794771920; retain until a later verified
  operation explicitly retires them. This is an operation, not a recurring purge.
- Market must use the same Housing interface and behavior: section → Queue /
  Favorites, personal flags, photo cards/public contacts, Viewed removal, undoable
  unfavorite, sorting, carousel, Back/Deck and new-findings-only summaries. No old
  queue reminders. Product-specific facts and source/topic selection differ.
- Node Tools main retains four unrelated local modifications and is eight commits
  behind origin/main. Fetch succeeded; safe pull aborted because those files
  would be overwritten. No files were stashed/discarded. A clean isolated worktree
  at /Users/alex/construction_side/node-tools/notifier-outcomes tracks origin/main
  on feat/notifier-outcomes at ec5b2f1 (0.12.3); safe fetch/pull succeeded there.
  It currently contains no implementation changes and may be removed when no
  longer needed. Resolve main integration/release without losing original edits.

## Remaining execution order

2. Move Vibecoding outcomes to Node Radar through Node Tools' existing technical
   pending/send/ack contract. Radar remains Alex-only and retains its sole Node
   Tools socket. Migrate cursor, pending outcomes and real receipts before
   disabling Notifier's Core consumer/removing its Vibecoding menu. No Core
   restart or execution permissions.
3. Create market-watch via the personal-repository bootstrap skill. One repo/app
   for astronomy (telescopes plus astronomical equipment) and digital pianos;
   OLX plus Allegro Lokalnie, Warsaw city, all prices, new/used. Exclude acoustic
   pianos, ordinary keyboards, wanted ads and rentals. Verify actual Polish
   categories/terms and native VPS access/pagination. HTTP first; Playwright only
   when ordinary rendering requires it and a VPS preflight succeeds. Blocking
   is an error, never empty success. Both connectors are required for this slice.
4. Add source/topic metadata and capabilities to Notifier feeds; use topic-scoped
   event membership, queue queries and subscriptions. Market → Astronomy/Digital
   pianos → Queue/Favorites. Reuse actor flags, photos/public contacts, sort,
   carousel and Back/Deck. Quiet initial inventory, one new-findings summary per
   topic, no queue reminders. Scan every 600s; feed capture every 900s, wall-clock
   boundaries without offsets. New IDs only; pure updates do not notify.
5. Add a bounded cursor-based raw climate-event Unix read endpoint to Node Tools
   for its configured indoor stream; no DB mounts or chart-average evaluation.
   Create home-watch via the personal-repository skill, read every 30s; Notifier
   consumes every 30s independently of listing feeds. Below 15 opens an episode;
   further thresholds are 14.5, 14.0, 13.5 and downward by 0.5 degrees Celsius.
   Exact 15 does not open; later thresholds trigger at or below. One alert per
   newly crossed threshold/episode, coalesce jumps and obsolete pending alerts.
   Rearm after two distinct consecutive fresh readings >=15.5; recovery is quiet.
   Persist cursor/rule/outbox atomically. Ignore duplicate/out-of-order/stale,
   failed and untrusted readings for transitions; failures are not zero degrees.
   Initial/reconnect reconcile latest fresh state without historical alert spam.
   Home UI shows measurement time/freshness/current rule state. Technical faults
   go to Radar; do not reenable disabled Raspberry policies automatically.
6. Independent versioned releases/deployments per verified slice. Existing bots
   keep their deployment forms; new collectors use separate native systemd units,
   config/data/users. No broker/shared writable DB/shared subscription service.
   Safe logs cover polls, scans, event IDs, subscription changes, retries and
   delivery receipts without secrets/contact/body content. Read back installed
   versions and use real deployed UI/API paths. Preserve rollback points.

## Acceptance requirements

Run each owner's required checks. Cover false new alerts with old queue entries,
all area aliases, rent boundaries excluding fees, no rooms, mixed-platform date
sort, unchanged flags, owner-only management, guest isolation and subscription
revocation/resubscription. Exercise actual menus, empty state, Viewed, Favorite
undo, photos, sorting and navigation. Verify both Market platforms from the VPS.
Test temperature boundaries, oscillation, jumps, recovery, missing data, clock
trust, restart and backlog. Verify Vibecoding handover without lost pending
outcomes or avoidable replay. Telegram acceptance is not proof of human reading.
