"""Non-destructive long-term persistent memory manager (memory/long_term.json)."""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_FILE = BASE_DIR / "memory" / "long_term.json"

DEFAULT_MEMORY: dict[str, Any] = {
    "identity": {
        "assistant": "DEX",
        "owner": "Operator",
        "workspace": "DEX // Mark LVII Terminal",
    },
    "facts": [],
    "monitors": [],
    "sessions": [],
}


def load_memory() -> dict[str, Any]:
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = dict(DEFAULT_MEMORY)
                merged.update(data)
                if not isinstance(merged.get("identity"), dict):
                    merged["identity"] = dict(DEFAULT_MEMORY["identity"])
                if not isinstance(merged.get("facts"), list):
                    merged["facts"] = []
                if not isinstance(merged.get("monitors"), list):
                    merged["monitors"] = []
                if not isinstance(merged.get("sessions"), list):
                    merged["sessions"] = []
                return merged
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_MEMORY))


def save_memory(data: dict[str, Any]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_fact(text: str, category: str = "general") -> dict[str, Any]:
    mem = load_memory()
    facts: list[dict[str, Any]] = mem.get("facts", [])
    entry = {
        "id": f"mem_{int(time.time() * 1000) % 1000000:06d}",
        "category": category,
        "text": text.strip(),
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    facts.append(entry)
    mem["facts"] = facts
    save_memory(mem)
    return entry


def search_facts(query: str) -> list[dict[str, Any]]:
    q = query.strip().lower()
    facts = load_memory().get("facts", [])
    if not q:
        return facts
    return [f for f in facts if q in f.get("text", "").lower() or q in f.get("category", "").lower()]


def remove_fact(fact_id_or_index: str) -> dict[str, Any] | None:
    mem = load_memory()
    facts: list[dict[str, Any]] = mem.get("facts", [])
    removed = None
    if fact_id_or_index.isdigit():
        idx = int(fact_id_or_index) - 1
        if 0 <= idx < len(facts):
            removed = facts.pop(idx)
    else:
        for i, item in enumerate(facts):
            if item.get("id") == fact_id_or_index:
                removed = facts.pop(i)
                break
    if removed:
        mem["facts"] = facts
        save_memory(mem)
    return removed


def clear_memory_facts() -> int:
    mem = load_memory()
    count = len(mem.get("facts", []))
    mem["facts"] = []
    save_memory(mem)
    return count


def record_session_summary(summary: str) -> None:
    mem = load_memory()
    sessions: list[dict[str, Any]] = mem.get("sessions", [])
    sessions.append({
        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": summary.strip(),
    })
    mem["sessions"] = sessions[-30:]
    save_memory(mem)
