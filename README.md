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

Use /start in a private chat to register and receive a welcome. Open Menu or
send /menu to see available sections. The numeric owner manages topic access
under Settings → Users. The optional housing_usernames list pins invited users by
Telegram ID and prepares a Housing subscription on their first /start. Opening
Menu checks the producer watermark before activating it. Viewed/Favorites
and carousel state are personal. Sort cycles platform publication time, platform update time and base rent.
Both new and remaining counts are validated against live digest members for each
recipient at delivery; viewed entries and rooms are excluded. Queue entry starts with newest publication. Unrelated input never reaches an
agent. Enable queue=true only for sources implementing the private queue/review API;
Vibecoding Core remains read-only. No producer database is mounted.

Housing alerts contain a new-findings count and View queue, without individual
apartment pushes. Empty scans and existing queues stay silent. Only new-finding alerts are sent,
available 24/7. Housing feed capture runs on quarter-hour
boundaries while source scans run every ten minutes. Known delivery receipts and source cursors survive updates and restarts.

See [configuration](config.example.toml), [business rules](BUSINESS.md),
[operations](docs/OPERATIONS.md) and [Compose](compose.yaml). This repository retains
its existing public visibility; credentials, runtime data and private payloads stay
outside Git. Tests alone use a public Core fixture; production imports no sibling.
