"""Time rule parsing and next-fire computation for Mark LVII routines."""

from __future__ import annotations

import datetime


def next_fire_time(schedule: str, now: datetime.datetime | None = None) -> str:
    """Compute a human-readable next fire timestamp from simple HH:MM or interval rules."""
    ref = now or datetime.datetime.now()
    clean = schedule.strip().lower()

    if ":" in clean and len(clean) <= 5:
        try:
            hh, mm = map(int, clean.split(":", 1))
            candidate = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if candidate <= ref:
                candidate += datetime.timedelta(days=1)
            return candidate.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass

    if clean.endswith("m") and clean[:-1].isdigit():
        mins = int(clean[:-1])
        return (ref + datetime.timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M")

    if clean.endswith("h") and clean[:-1].isdigit():
        hrs = int(clean[:-1])
        return (ref + datetime.timedelta(hours=hrs)).strftime("%Y-%m-%d %H:%M")

    return "On demand / manual trigger"
