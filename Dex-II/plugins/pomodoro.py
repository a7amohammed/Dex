"""Pomodoro focus session timer plugin."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome

BASE_DIR = Path(__file__).resolve().parent.parent
POMO_FILE = BASE_DIR / "memory" / ".pomodoro.json"

TOOL = {
    "name": "pomodoro",
    "description": "Manage Pomodoro deep-work focus timers (`pomodoro start [mins]|status|stop`).",
    "commands": ["pomodoro", "pomo"],
}


def _load() -> dict[str, Any]:
    if POMO_FILE.exists():
        try:
            return json.loads(POMO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"active": False, "label": "Deep Work", "duration_min": 25, "started_at": 0.0, "completed_sessions": 0}


def _save(state: dict[str, Any]) -> None:
    POMO_FILE.parent.mkdir(parents=True, exist_ok=True)
    POMO_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def handler(_cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    parts = arg.split(maxsplit=1) if arg else []
    sub = parts[0].lower() if parts else "status"
    rest = parts[1].strip() if len(parts) > 1 else ""
    state = _load()

    if sub == "start":
        mins = 25
        label = "Deep Work"
        if rest:
            tokens = rest.split(maxsplit=1)
            if tokens[0].isdigit():
                mins = max(1, min(120, int(tokens[0])))
                label = tokens[1] if len(tokens) > 1 else "Deep Work"
            else:
                label = rest
        state["active"] = True
        state["duration_min"] = mins
        state["label"] = label
        state["started_at"] = time.time()
        _save(state)
        return ToolOutcome(
            status="started",
            summary=f"Pomodoro started: {mins}m ({label})",
            lines=[f"POMODORO TIMER ENGAGED  ·  {mins} minutes ({label})"],
        )

    if sub == "stop":
        if not state.get("active"):
            return ToolOutcome(status="done", summary="No active Pomodoro timer.", lines=["No Pomodoro session is currently running."])
        state["active"] = False
        _save(state)
        return ToolOutcome(status="done", summary="Pomodoro stopped.", lines=["Pomodoro timer stopped."])

    if not state.get("active"):
        return ToolOutcome(
            status="done",
            summary="Pomodoro idle.",
            lines=[
                f"Pomodoro idle · Completed sessions: {state.get('completed_sessions', 0)}",
                "Start one with: pomodoro start 25 Stark Armor Refactor",
            ],
        )

    elapsed = time.time() - state["started_at"]
    total = state["duration_min"] * 60
    remaining = max(0, int(total - elapsed))
    if remaining == 0:
        state["active"] = False
        state["completed_sessions"] = state.get("completed_sessions", 0) + 1
        _save(state)
        return ToolOutcome(
            status="done",
            summary="Pomodoro complete!",
            lines=[f"POMODORO COMPLETE  ·  '{state['label']}' finished ({state['duration_min']}m)."],
        )
    mm, ss = divmod(remaining, 60)
    return ToolOutcome(
        status="done",
        summary=f"Pomodoro remaining: {mm:02d}:{ss:02d}",
        lines=[f"POMODORO ACTIVE  ·  {state['label']}  ·  {mm:02d}:{ss:02d} remaining"],
    )
