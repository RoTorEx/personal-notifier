# Personal Notifier

Private Telegram notifications and an owner-only Home deck. Vibecoding retains its
push notices; its menu entry currently shows Under construction. Housing opens a section menu with separate Queue and Favorites carousels with Viewed/Favorite, source links, public phone copying and
separate carousel versus Back/Deck navigation. Carousel buttons update the existing screen; returning from a photo to a text menu
replaces that screen without placeholder images. captions are compact and omit empty fields. All interface
text is English.

```sh
make install
make check
uv run --frozen personal-notifier --config /path/to/bot.toml
```

Use /menu or /housing in the configured owner's private chat. The numeric owner receives all notices. Optional housing_usernames invite housing-only
participants; each first private /start pins the Telegram user ID. Viewed/Favorites
and carousel state are personal. Sort cycles platform publication time, platform update time and base rent.
Both new and remaining counts are validated against live digest members for each
recipient at delivery; viewed entries and rooms are excluded. Queue entry starts with newest publication. Unrelated input never reaches an
agent. Enable queue=true only for sources implementing the private queue/review API;
Vibecoding Core remains read-only. No producer database is mounted.

Housing alerts contain a new-findings count and View queue, without individual
apartment pushes. Empty scans stay silent; nonempty queues may remind once per hour from 12:00 to 00:00 Europe/Warsaw.
New-finding alerts remain available 24/7. Housing feed capture runs on quarter-hour
boundaries while source scans run every ten minutes. Known delivery receipts and source cursors survive updates and restarts.

See [configuration](config.example.toml), [business rules](BUSINESS.md),
[operations](docs/OPERATIONS.md) and [Compose](compose.yaml). This repository retains
its existing public visibility; credentials, runtime data and private payloads stay
outside Git. Tests alone use a public Core fixture; production imports no sibling.
