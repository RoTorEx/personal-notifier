# Personal Notifier

One outbound-only Telegram feed for personal events. It pulls notifications from
Vibecoding Core and Housing Watch. No commands, Telegram update polling or agent control. Optional photo cards
can include a native Copy phone button, handled entirely by Telegram. Existing Telegram identity and successful delivery receipts survive
its rename from Telegram Vibecoding.

```sh
make install
make check
uv run --frozen personal-notifier --config /path/to/bot.toml
```

See [configuration](config.example.toml), [business contract](BUSINESS.md),
[operations](docs/OPERATIONS.md), and the independent [Compose service](compose.yaml).
Housing Watch owns listings and collection; this service owns cursors and delivery.
No source code imports another producer implementation. Core fixtures are used
only by tests; override CORE_SOURCE when its checkout is elsewhere.

This existing repository retains its original public visibility and Git history.
No credentials, runtime databases or source payloads belong in Git.
