# Missing-notification incident

- Fix the producer/consumer photo_urls contract through real FeedClient validation.
- Add a queue-summary-only event read to avoid unrelated listing-update backlog;
  prevent collection-scope metadata from generating artificial source updates.
- Audit every Housing/Market category against persisted source decisions and
  representative live offers; preserve the owner/Ira scopes and review state.
- Publish/deploy verified patches. Recover only genuinely missed post-reset
  discoveries in one catch-up event per topic, through the normal sender and
  real recipient receipts, without replaying historical individual summaries.
- Record evidence, remaining platform limitations, recovery points and cleanup.

Follow-up in order, after this incident is resolved:

- Add nationwide market.keyboards on OLX and Allegro Lokalnie for complete
  Lofree Flow Lite84 first generation and Flow Lite 2 84, including Lite 84,
  Lite84 and V2 spelling. Exclude non-Lite Flow/Flow 2, Lite100 and standalone
  switches/keycaps/cases. Accept new/used/display stock. Reuse per-person
  Queue/Favorites/Viewed and quiet initial inventory with new-identity digests.
- Show price, condition, source, link and location. Price references, not
  automatic purchases: gen1 used <=200 PLN, gen1 new <=350, Lite2 new <=450.
- Preserve Housing and other Market topics. The prior reset covers the topics
  existing at that reset; do not hide the new keyboard baseline accidentally.

Current incident evidence and state:

- Live versions 0.3.4 / 0.6.2 restored real owner deliveries: Housing event 25116
  -> message 208, Astronomy 25117 -> 209, Pianos 25118 -> 210, Outdoor 25119 -> 211.
- Protected recovery: /srv/web-watch/recovery/gallery-delivery-0.3.4 and
  /srv/personal-notifier/recovery/gallery-delivery-0.6.2. All previous flags,
  subscriptions and original receipts were preserved. Ira delivery is forbidden
  by Telegram and remains pending; fix the hot retry loop without dropping it.
- Detailed direct checks found all 4 recovered pianos active and newly published
  16-18 November. Astronomy's preliminary 9 included a MAK sailboat, EQ audio,
  EQ thermostat and cleaning kit. One genuine new EQ5 is now 404; cleaning kit
  is 410. Real MAK 127 is active but originally published 13 October, refreshed
  17 November. Two old solar filters and a wedge predate the reset.
- Local pending patches: matcher v6 plus post-reset temporal baseline handling
  (target 0.3.5); persisted denied-recipient retry (target 0.6.3). Validate, ship,
  repair only false historical/expired memberships, edit the 4 existing catch-up
  messages to current correct counts, retain genuine receipt IDs.
- Owned scratch: ~/construction_side/web-watch/notification-audit and
  /home/alex/missing-notifications-audit, containing full audit and scripts.
  Commit the final English incident report under Web Watch docs/incidents.

Keyboard clarification pending from the owner: the supplied table lists Flow
Lite84 <=220 PLN (very high), Flow84 V1 <=320 (very high), Flow 2 84/68 <=400
(high). Asked whether this replaces the first list (removing Lite 2 84) or adds
to it. All earlier all-condition/no-purchase/interface constraints still apply.
