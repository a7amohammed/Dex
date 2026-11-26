"""Persistent mission notes and scheduled reminders."""

from __future__ import annotations

import datetime
from typing import Any

from core.confirm import issue_confirmation
from core.outcome import ToolOutcome
from core.undo import push_undo, register_undo_handler
from memory.memory_manager import add_fact, load_memory, remove_fact, save_memory

TOOL = {
    "name": "reminder",
    "description": "Manage persistent mission reminders and long-term memory facts.",
    "commands": ["note", "remember", "memory", "forget"],
}


def _undo_add_fact(payload: dict[str, Any]) -> str:
    fid = payload.get("id")
    if fid:
        remove_fact(fid)
        return f"Removed memory entry {fid}."
    return "Nothing to undo."


register_undo_handler("add_fact", _undo_add_fact)


def handler(cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    if cmd == "remember":
        if not arg:
            return ToolOutcome(status="failed", summary="Usage: remember <fact or preference>")
        entry = add_fact(arg, category="fact")
        push_undo("add_fact", f"Remember '{arg[:32]}'", {"id": entry["id"]})
        return ToolOutcome(
            status="done",
            summary=f"Stored memory fact {entry['id']}.",
            lines=[f"Committed to long-term memory [{entry['id']}]: \"{entry['text']}\" (Type `undo` to revert.)"],
        )

    if cmd == "forget":
        if not arg:
            return ToolOutcome(status="failed", summary="Usage: forget <index_or_id | all>")
        if arg.lower() == "all":
            token = issue_confirmation("clear_memory", "Erase all stored long-term memory facts")
            return ToolOutcome(
                status="ask",
                summary="Confirmation required to erase all long-term memory facts.",
                lines=[
                    "IRREVERSIBLE ACTION GATE  ·  Erase all long-term memory facts",
                    f"  To proceed, run: confirm {token}",
                ],
                confirm_token=token,
            )
        removed = remove_fact(arg)
        if not removed:
            return ToolOutcome(status="failed", summary=f"Memory entry '{arg}' not found.")
        return ToolOutcome(status="done", summary=f"Forgot '{removed['text']}'.", lines=[f"Removed memory entry: \"{removed['text']}\""])

    if cmd == "memory":
        mem = load_memory()
        facts = mem.get("facts", [])
        if not facts:
            return ToolOutcome(status="done", summary="Long-term memory is empty.", lines=["Long-term memory contains 0 facts. Store one with: remember <fact>"])
        lines = ["LONG-TERM MEMORY (memory/long_term.json)", "------------------------------------------------------------------------"]
        for i, f in enumerate(facts, 1):
            lines.append(f"  {i:02d}. [{f['id']}] ({f.get('created_at', '')}) {f['text']}")
        return ToolOutcome(status="done", summary=f"{len(facts)} facts stored.", lines=lines)

    # `note` command
    parts = arg.split(maxsplit=1) if arg else []
    sub = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""
    if sub == "add" and rest:
        entry = add_fact(rest, category="note")
        push_undo("add_fact", f"Add note '{rest[:32]}'", {"id": entry["id"]})
        return ToolOutcome(status="done", summary="Note saved.", lines=[f"Mission note recorded [{entry['id']}]: \"{entry['text']}\""])
    if sub == "clear":
        mem = load_memory()
        mem["facts"] = [f for f in mem.get("facts", []) if f.get("category") != "note"]
        save_memory(mem)
        return ToolOutcome(status="done", summary="Notes cleared.", lines=["Mission notes cleared."])

    notes = [f for f in load_memory().get("facts", []) if f.get("category") == "note"]
    if not notes:
        return ToolOutcome(status="done", summary="No mission notes.", lines=["Mission log is empty. Add one with: note add <message>"])
    lines = ["STARK MISSION LOG", "------------------------------------------------------------------------"]
    for i, n in enumerate(notes, 1):
        lines.append(f"  {i:02d}. [{n.get('created_at', '')}] {n['text']}")
    return ToolOutcome(status="done", summary=f"{len(notes)} mission notes.", lines=lines)
