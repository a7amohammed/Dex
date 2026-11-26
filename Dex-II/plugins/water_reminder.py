"""Hydration intake tracker plugin."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome

BASE_DIR = Path(__file__).resolve().parent.parent
WATER_FILE = BASE_DIR / "memory" / ".water_log.json"

TOOL = {
    "name": "water_reminder",
    "description": "Track daily hydration intake (`water log [ml]|status`).",
    "commands": ["water", "hydrate"],
}


def _load() -> dict[str, Any]:
    today = datetime.date.today().isoformat()
    if WATER_FILE.exists():
        try:
            data = json.loads(WATER_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
        except Exception:
            pass
    return {"date": today, "ml": 0, "goal_ml": 2500}


def _save(data: dict[str, Any]) -> None:
    WATER_FILE.parent.mkdir(parents=True, exist_ok=True)
    WATER_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def handler(_cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    parts = arg.split() if arg else []
    sub = parts[0].lower() if parts else "status"
    data = _load()

    if sub in ("log", "add"):
        amt = 250
        if len(parts) > 1 and parts[1].isdigit():
            amt = max(50, min(2000, int(parts[1])))
        data["ml"] += amt
        _save(data)
        pct = min(100.0, round((data["ml"] / data["goal_ml"]) * 100, 1))
        return ToolOutcome(
            status="done",
            summary=f"Logged {amt} ml ({data['ml']}/{data['goal_ml']} ml).",
            lines=[f"Logged +{amt} ml hydration · Today: {data['ml']} / {data['goal_ml']} ml ({pct}%)"],
        )

    pct = min(100.0, round((data["ml"] / data["goal_ml"]) * 100, 1))
    return ToolOutcome(
        status="done",
        summary=f"Hydration: {data['ml']}/{data['goal_ml']} ml",
        lines=[
            f"HYDRATION TELEMETRY ({data['date']})",
            f"  Intake : {data['ml']} / {data['goal_ml']} ml ({pct}%)",
            "  Log    : water log 250",
        ],
    )
