"""Queue reminders run from noon to midnight in Europe/Warsaw; alerts are separate."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def reminders_allowed(at=None):
    at = at or datetime.now(UTC)
    if isinstance(at, str):
        at = datetime.fromisoformat(at.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("Reminder time must include its time zone")
    return at.astimezone(ZoneInfo("Europe/Warsaw")).hour >= 12
