"""Routine engine managing memory/routines.json, quiet hours, and background scheduling."""

from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path
from typing import Any, Callable

from core.routines.rules import next_fire_time
from memory.config_manager import load_settings, save_settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROUTINES_FILE = BASE_DIR / "memory" / "routines.json"

DEFAULT_ROUTINES: list[dict[str, Any]] = [
    {
        "name": "morning_brief",
        "schedule": "08:00",
        "command": "diag",
        "description": "Morning hardware diagnostics & suit integrity sweep",
        "enabled": True,
        "last_run": None,
    },
    {
        "name": "perimeter_watch",
        "schedule": "4h",
        "command": "status",
        "description": "Periodic system load & memory headroom check",
        "enabled": True,
        "last_run": None,
    },
]


def load_routines() -> list[dict[str, Any]]:
    if ROUTINES_FILE.exists():
        try:
            data = json.loads(ROUTINES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_ROUTINES))


def save_routines(routines: list[dict[str, Any]]) -> None:
    ROUTINES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROUTINES_FILE.write_text(json.dumps(routines, indent=2), encoding="utf-8")


def add_routine(name: str, schedule: str, command: str, description: str = "") -> dict[str, Any]:
    routines = load_routines()
    clean_name = name.strip().lower().replace(" ", "_")
    routines = [r for r in routines if r.get("name") != clean_name]
    entry = {
        "name": clean_name,
        "schedule": schedule.strip(),
        "command": command.strip(),
        "description": description or f"Executes `{command.strip()}` at `{schedule.strip()}`",
        "enabled": True,
        "last_run": None,
        "next_fire": next_fire_time(schedule),
    }
    routines.append(entry)
    save_routines(routines)
    return entry


def remove_routine(name: str) -> dict[str, Any] | None:
    clean = name.strip().lower().replace(" ", "_")
    routines = load_routines()
    removed = None
    kept = []
    for r in routines:
        if r.get("name") == clean and removed is None:
            removed = r
        else:
            kept.append(r)
    if removed:
        save_routines(kept)
    return removed


def mark_routine_run(name: str) -> dict[str, Any] | None:
    clean = name.strip().lower().replace(" ", "_")
    routines = load_routines()
    target = None
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in routines:
        if r.get("name") == clean:
            r["last_run"] = now
            r["next_fire"] = next_fire_time(r.get("schedule", ""))
            target = r
            break
    if target:
        save_routines(routines)
    return target


def is_quiet_hours() -> bool:
    qh = load_settings().get("quiet_hours", {})
    if not qh.get("enabled"):
        return False
    hr = datetime.datetime.now().hour
    start, end = int(qh.get("start", 23)), int(qh.get("end", 7))
    if start > end:
        return hr >= start or hr < end
    return start <= hr < end


def set_quiet_hours(enabled: bool, start: int = 23, end: int = 7) -> dict[str, Any]:
    settings = load_settings()
    settings["quiet_hours"] = {"enabled": enabled, "start": start, "end": end}
    save_settings(settings)
    return settings["quiet_hours"]


def is_routine_due(routine: dict[str, Any], now: datetime.datetime | None = None) -> bool:
    if not routine.get("enabled", True):
        return False
    ref = now or datetime.datetime.now()
    next_str = routine.get("next_fire")
    if not next_str or next_str == "On demand / manual trigger":
        return False
    try:
        due_dt = datetime.datetime.strptime(next_str, "%Y-%m-%d %H:%M")
        return ref >= due_dt
    except ValueError:
        return False


class RoutineScheduler:
    """Background thread evaluating due routines and respecting quiet hours."""

    def __init__(self, dispatch_fn: Callable[[str], dict[str, Any]], on_notify: Callable[[str], None]) -> None:
        self.dispatch_fn = dispatch_fn
        self.on_notify = on_notify
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while not self._stop.wait(15.0):
            if not load_settings().get("performance", {}).get("background_scheduler", True):
                continue
            if is_quiet_hours():
                continue
            now = datetime.datetime.now()
            for r in load_routines():
                if is_routine_due(r, now):
                    mark_routine_run(r["name"])
                    res = self.dispatch_fn(r.get("command", "status"))
                    self.on_notify(f"Routine '{r['name']}' ran: {res.get('summary', 'Done')}")
