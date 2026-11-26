"""Shared persistent undo stack for reversible Mark LVII actions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent.parent
UNDO_FILE = BASE_DIR / "memory" / ".undo_stack.json"

_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {}


def register_undo_handler(kind: str, fn: Callable[[dict[str, Any]], str]) -> None:
    _HANDLERS[kind] = fn


def _load_stack() -> list[dict[str, Any]]:
    if UNDO_FILE.exists():
        try:
            data = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_stack(stack: list[dict[str, Any]]) -> None:
    UNDO_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNDO_FILE.write_text(json.dumps(stack[-25:], indent=2), encoding="utf-8")


def push_undo(kind: str, description: str, payload: dict[str, Any]) -> None:
    stack = _load_stack()
    stack.append({
        "kind": kind,
        "description": description,
        "payload": payload,
        "timestamp": time.time(),
    })
    _save_stack(stack)


def list_undo() -> list[dict[str, Any]]:
    return _load_stack()


def pop_and_undo() -> tuple[bool, str]:
    stack = _load_stack()
    if not stack:
        return False, "Undo stack is empty — no reversible actions recorded."
    entry = stack.pop()
    kind = entry.get("kind", "")
    fn = _HANDLERS.get(kind)
    if not fn:
        _save_stack(stack)
        return False, f"No undo handler registered for action '{kind}'."
    try:
        msg = fn(entry.get("payload", {}))
        _save_stack(stack)
        return True, f"Reverted ({entry.get('description', kind)}): {msg}"
    except Exception as exc:
        return False, f"Undo failed: {exc}"
