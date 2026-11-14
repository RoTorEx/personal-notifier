"""Private Telegram configuration, independent of the Core implementation."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FeedSource:
    name: str
    socket: Path
    poll_seconds: float = 15
    queue: bool = False


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    # Source collectors have no Telegram credentials.
    runtime_dir: Path
    token_file: Path
    allowed_user_id: int = 0
    host_id: str = "vps"
    bot_username: str = ""
    web_url: str = "https://vibecoding.com"
    housing_usernames: tuple[str, ...] = ()
    core_enabled: bool = True
    sources: tuple[FeedSource, ...] = ()
    confirmation_required: bool = False
    confirmation_url: str = ""
    confirmation_host: str = "127.0.0.1"
    confirmation_port: int = 8790

    @property
    def socket(self) -> Path:
        return self.runtime_dir / "engine.sock"

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = (
            path
            or Path(
                os.environ.get("PERSONAL_NOTIFIER_CONFIG", "~/.config/personal-notifier/bot.toml")
            ).expanduser()
        )
        values = tomllib.loads(path.read_text()) if path.exists() else {}
        sources: list[FeedSource] = []
        import re

        for source in values.pop("sources", []):
            name = source["name"]
            if (
                not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", name)
                or name == "vibecoding"
                or any(s.name == name for s in sources)
            ):
                raise ValueError("Source names must be unique and cannot be vibecoding")
            socket = Path(source["socket"]).expanduser()
            interval = float(source.get("poll_seconds", 15))
            if not socket.is_absolute() or interval < 1:
                raise ValueError("Sources require absolute socket paths and positive polling intervals")
            queue = source.get("queue", False)
            if type(queue) is not bool:
                raise ValueError("queue must be boolean")
            sources.append(FeedSource(name, socket, interval, queue))
        values["sources"] = tuple(sources)
        usernames = values.get("housing_usernames", [])
        if not isinstance(usernames, (list, tuple)) or any(
            not isinstance(n, str) or not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", n.lstrip("@"))
            for n in usernames
        ):
            raise ValueError("housing_usernames must contain Telegram usernames")
        values["housing_usernames"] = tuple(n.lstrip("@").lower() for n in usernames)
        if unknown := set(values) - set(cls.__dataclass_fields__):
            raise ValueError(f"Unknown Telegram configuration keys: {', '.join(sorted(unknown))}")
        data = Path(values.pop("data_dir", "~/.local/state/personal-notifier")).expanduser()
        runtime = Path(values.pop("runtime_dir", str(data / "run"))).expanduser()
        token = Path(values.pop("token_file", "~/.config/personal-notifier/bot-token")).expanduser()
        return cls(data_dir=data, runtime_dir=runtime, token_file=token, **values)

    def validate_web_url(self) -> None:
        from urllib.parse import urlsplit

        url = urlsplit(self.web_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("web_url must be an HTTP(S) origin without credentials, query or fragment")

    def prepare(self) -> None:
        if self.confirmation_required:
            from urllib.parse import urlsplit

            url = urlsplit(self.confirmation_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("Confirmation requires a trusted HTTPS URL without credentials or query")
        for path in [self.data_dir, self.runtime_dir, self.data_dir / "uploads"]:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.chmod(0o700)
        if len(os.fsencode(self.socket)) > 100:
            raise ValueError("runtime_dir is too long for a portable Unix socket")

    def read_token(self) -> str:
        if self.allowed_user_id <= 0:
            raise ValueError("Configure allowed_user_id before starting the bot")
        if self.token_file.stat().st_mode & 0o077:
            raise ValueError("The bot token file must have mode 600")
        token = self.token_file.read_text().strip()
        if ":" not in token or any(c.isspace() for c in token):
            raise ValueError("Invalid bot token file")
        return token
