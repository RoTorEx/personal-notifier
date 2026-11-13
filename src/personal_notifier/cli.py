"""Personal notification process entrypoint and container readiness check."""

import argparse
import asyncio
import logging
import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from personal_notifier import __version__
from personal_notifier.config import Settings


def healthy(settings: Settings, instance_file=Path("/tmp/personal-notifier-instance")) -> bool:
    try:
        with closing(sqlite3.connect((settings.data_dir / "bot.db").as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT value FROM meta WHERE key='bot_pid'").fetchone()
            instance = db.execute("SELECT value FROM meta WHERE key='bot_instance'").fetchone()
            heartbeat = db.execute("SELECT value FROM meta WHERE key='poll_heartbeat'").fetchone()
        if not row or not instance or instance[0] != instance_file.read_text().strip():
            return False
        if not heartbeat or not 0 <= time.time() - float(heartbeat[0]) <= 120:
            return False
        os.kill(int(row[0]), 0)
        return True
    except (OSError, ValueError, sqlite3.Error):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--capabilities", action="store_true", help="Report the notification-only runtime contract"
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.capabilities:
        print("notifications-only")
        return
    os.umask(0o077)
    settings = Settings.load(args.config)
    if args.health:
        if not healthy(settings):
            raise SystemExit(1)
        return
    from personal_notifier.notifier import run

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print("Personal Notifier failed: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
