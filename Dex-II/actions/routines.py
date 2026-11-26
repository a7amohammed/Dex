"""Routines & quiet hours management action."""

from __future__ import annotations

from typing import Any

from core.outcome import ToolOutcome
from core.routines.engine import (
    add_routine,
    is_quiet_hours,
    load_routines,
    mark_routine_run,
    remove_routine,
    set_quiet_hours,
)
from core.undo import push_undo, register_undo_handler

TOOL = {
    "name": "routines",
    "description": "Manage automated routines and quiet hours.",
    "commands": ["routine", "routines"],
}


def _undo_remove_routine(payload: dict[str, Any]) -> str:
    r = payload.get("routine")
    if isinstance(r, dict):
        add_routine(r["name"], r.get("schedule", "daily"), r.get("command", "status"), r.get("description", ""))
        return f"Restored routine '{r['name']}'."
    return "Nothing to restore."


register_undo_handler("remove_routine", _undo_remove_routine)


def handler(_cmd: str, arg: str, ctx: dict[str, Any]) -> ToolOutcome:
    parts = arg.split() if arg else []
    sub = parts[0].lower() if parts else "list"

    if sub == "add":
        if len(parts) < 4:
            return ToolOutcome(status="failed", summary="Usage: routine add <name> <schedule:08:00|4h> <command>")
        name, sched, cmd_str = parts[1], parts[2], " ".join(parts[3:])
        entry = add_routine(name, sched, cmd_str)
        return ToolOutcome(
            status="done",
            summary=f"Routine '{entry['name']}' scheduled.",
            lines=[
                f"ROUTINE REGISTERED  ·  {entry['name']}",
                f"  Schedule : {entry['schedule']} (Next: {entry.get('next_fire', 'on demand')})",
                f"  Command  : {entry['command']}",
            ],
        )

    if sub == "remove":
        if len(parts) < 2:
            return ToolOutcome(status="failed", summary="Usage: routine remove <name>")
        removed = remove_routine(parts[1])
        if not removed:
            return ToolOutcome(status="failed", summary=f"Routine '{parts[1]}' not found.")
        push_undo("remove_routine", f"Remove routine {removed['name']}", {"routine": removed})
        return ToolOutcome(
            status="done",
            summary=f"Removed routine '{removed['name']}'.",
            lines=[f"Removed routine '{removed['name']}'. (Type `undo` to restore.)"],
        )

    if sub == "run":
        if len(parts) < 2:
            return ToolOutcome(status="failed", summary="Usage: routine run <name>")
        r = mark_routine_run(parts[1])
        if not r:
            return ToolOutcome(status="failed", summary=f"Routine '{parts[1]}' not found.")
        dispatch = ctx.get("dispatch")
        if callable(dispatch):
            res = dispatch(r["command"])
            sub_lines = res.get("lines", [])
        else:
            sub_lines = [f"Executed `{r['command']}`"]
        return ToolOutcome(
            status="done",
            summary=f"Routine '{r['name']}' executed.",
            lines=[f"ROUTINE EXECUTED  ·  {r['name']} ({r['command']})", *sub_lines],
        )

    if sub == "quiet":
        state_arg = parts[1].lower() if len(parts) > 1 else ""
        if state_arg in ("on", "enable", "true"):
            qh = set_quiet_hours(True)
            return ToolOutcome(status="done", summary="Quiet hours enabled.", lines=[f"Quiet hours enabled ({qh['start']:02d}:00–{qh['end']:02d}:00)."])
        if state_arg in ("off", "disable", "false"):
            qh = set_quiet_hours(False)
            return ToolOutcome(status="done", summary="Quiet hours disabled.", lines=["Quiet hours disabled."])
        return ToolOutcome(status="done", summary=f"Quiet hours active now: {is_quiet_hours()}", lines=[f"Quiet hours currently active: {is_quiet_hours()}. Use `routine quiet on|off`."])

    routines = load_routines()
    lines = ["CONFIGURED ROUTINES", "------------------------------------------------------------------------"]
    for r in routines:
        last = r.get("last_run") or "never"
        lines.append(f"  {r['name']:<16} [{r['schedule']:<6}]  cmd=`{r['command']}`  last={last}")
    lines.append("")
    lines.append("Commands: routine add <name> <08:00|4h> <cmd> | routine run <name> | routine remove <name>")
    return ToolOutcome(status="done", summary=f"{len(routines)} routines loaded.", lines=lines)
