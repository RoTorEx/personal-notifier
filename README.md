# Personal Notifier

Private Telegram notifications and an owner-only Home deck. Vibecoding retains its
push notices; its menu entry currently shows Under construction. Housing opens the
newest-first queue with Viewed/Favorite, source links, public phone copying and
separate carousel versus Back/Deck navigation. Buttons update the existing screen,
including View queue; captions are compact and omit empty fields. All interface
text is English.

```sh
make install
make check
uv run --frozen personal-notifier --config /path/to/bot.toml
```

Use /menu or /housing in the configured owner's private chat. Only that numeric
Telegram ID receives notices or controls the bot. Unrelated input never reaches an
agent. Enable queue=true only for sources implementing the private queue/review API;
Vibecoding Core remains read-only. No producer database is mounted.

Housing alerts contain a new-findings count and View queue, without individual
apartment pushes. Empty scans stay silent; nonempty queues may remind every 30
minutes. Known delivery receipts and source cursors survive updates and restarts.

See [configuration](config.example.toml), [business rules](BUSINESS.md),
[operations](docs/OPERATIONS.md) and [Compose](compose.yaml). This repository retains
its existing public visibility; credentials, runtime data and private payloads stay
outside Git. Tests alone use a public Core fixture; production imports no sibling.
