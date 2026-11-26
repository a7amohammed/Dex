"""Persistent shopping list plugin with undo support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome
from core.undo import push_undo, register_undo_handler

BASE_DIR = Path(__file__).resolve().parent.parent
SHOP_FILE = BASE_DIR / "memory" / ".shopping_list.json"

TOOL = {
    "name": "shopping_list",
    "description": "Manage a persistent shopping list (`shop add|list|done|clear`).",
    "commands": ["shop", "shopping"],
}


def _load() -> list[dict[str, Any]]:
    if SHOP_FILE.exists():
        try:
            return json.loads(SHOP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(items: list[dict[str, Any]]) -> None:
    SHOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHOP_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _undo_shop(payload: dict[str, Any]) -> str:
    prev = payload.get("previous")
    if isinstance(prev, list):
        _save(prev)
        return "Restored previous shopping list state."
    return "Nothing to restore."


register_undo_handler("shopping_list", _undo_shop)


def handler(_cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    parts = arg.split(maxsplit=1) if arg else []
    sub = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""
    items = _load()

    if sub == "add" and rest:
        push_undo("shopping_list", f"Add '{rest}' to shopping list", {"previous": list(items)})
        items.append({"item": rest, "done": False})
        _save(items)
        return ToolOutcome(status="done", summary=f"Added '{rest}'.", lines=[f"Added '{rest}' to shopping list. (Type `undo` to revert.)"])

    if sub == "done" and rest:
        push_undo("shopping_list", f"Mark '{rest}' done", {"previous": [dict(x) for x in items]})
        for it in items:
            if it["item"].lower() == rest.lower() or (rest.isdigit() and items.index(it) == int(rest) - 1):
                it["done"] = True
                _save(items)
                return ToolOutcome(status="done", summary=f"Checked off '{it['item']}'.", lines=[f"Checked off: {it['item']}"])
        return ToolOutcome(status="failed", summary=f"Item '{rest}' not found.")

    if sub == "clear":
        push_undo("shopping_list", "Clear shopping list", {"previous": list(items)})
        _save([])
        return ToolOutcome(status="done", summary="Shopping list cleared.", lines=["Shopping list cleared. (Type `undo` to restore.)"])

    if not items:
        return ToolOutcome(status="done", summary="Shopping list empty.", lines=["Shopping list is empty. Add items with: shop add <item>"])

    lines = ["SHOPPING LIST", "------------------------------------------------------------------------"]
    for i, it in enumerate(items, 1):
        mark = "[x]" if it["done"] else "[ ]"
        lines.append(f"  {i:02d}. {mark} {it['item']}")
    return ToolOutcome(status="done", summary=f"{len(items)} items.", lines=lines)
