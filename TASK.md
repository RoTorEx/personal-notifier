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

## Accepted architecture and remaining execution order

The owner superseded the separate Market Watch/Home Watch design:
- The former housing-watch repo is renamed RoTorEx/web-watch, with its Git history
  and private visibility preserved. Local path is projects/home/web-watch. It owns
  housing and listing modules, one observations/review database, shared source
  connectors and the private interactive API. The existing native service/state
  identity remains compatible during cutover; no queue or event reset.
- Personal Notifier remains an independent repo/application/database. Connections
  are notification-only (Home temperature) or notifications plus interactive object
  collections (Housing/Market). Product topics determine subscriptions separately
  from connection capabilities. Node Radar remains the technical Alex-only bot.
- No new project/context/deployment repository or separate Home service. Both
  product repos remain in home. Do not create market-watch or home-watch.

1. Release/deploy optional Home temperature integration inside Notifier. The
   implementation passes 213 checks at the last checkpoint; refresh checks after
   final edits. Verify socket group/mount permissions, live source freshness,
   numeric recipients, subscription isolation, installed artifact, health and
   Home status UI without generating synthetic production cold alarms.
2. Complete Web Watch's listing module for OLX and Allegro Lokalnie, Warsaw city,
   all prices, new/used: astronomy (telescopes and equipment) and digital pianos.
   Exclude rental/wanted offers, ordinary keyboards and acoustic pianos. Verified
   platform routes: Allegro telescope category 124894 and digital pianos 122803;
   OLX telescope offers use category 100, digital pianos 4582. Verify accessory
   categories before enabling them. Native httpx preflight works on the VPS;
   urllib gets 403 and is not a substitute source-access check. Allegro ItemList
   JSON-LD works on native VPS. Preserve source metadata; never fabricate dates.
   Shared per-topic queue/event API and identical Notifier UI for Housing/Market:
   Queue/Favorites, photo/public contacts, Viewed, undoable unfavorite, sort,
   arrows, Back/Deck. Quiet initial baseline; new-ID digest summaries only.
   Scan every 600s, capture every 900s aligned, no old-queue reminders. Preserve
   the owner's queue-clear cutoff and all existing flags. Keep module source
   errors independent and validate cross-topic read/write boundaries.
3. Move Vibecoding outcomes to Radar through Node Tools' technical pending/send/ack
   contract. Preserve cursor, pending work and real receipts through handover;
   remove Notifier's Core consumer/menu only after verified replacement. No Core
   restart or execution access. Node Tools original checkout has unrelated edits;
   its safe pull is unresolved. Use the retained clean worktree for isolated work,
   but reconcile release integration without overwriting the original changes.
4. Independently release/deploy verified slices, with backups before migrations,
   safe activity logs, exact installed revisions and consumer-level verification.

## Acceptance requirements

Run each owner's required checks. Cover false new alerts with old queue entries,
all area aliases, rent boundaries excluding fees, no rooms, mixed-platform date
sort, unchanged flags, owner-only management, guest isolation and subscription
revocation/resubscription. Exercise actual menus, empty state, Viewed, Favorite
undo, photos, sorting and navigation. Verify both Market platforms from the VPS.
Test adaptive 600/60-second polling, five-minute cold alarms without any
0.5-degree change, simultaneous-trigger coalescing, stale-data repeat suppression,
restart without replay bursts, distinct-sample trend handling, temperature boundaries, oscillation, jumps, recovery, missing data, clock
trust, restart and backlog. Verify Vibecoding handover without lost pending
outcomes or avoidable replay. Telegram acceptance is not proof of human reading.
