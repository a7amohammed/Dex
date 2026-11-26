"""Spaced-repetition flashcard review plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome

BASE_DIR = Path(__file__).resolve().parent.parent
CARDS_FILE = BASE_DIR / "memory" / ".flashcards.json"

DEFAULT_CARDS = [
    {"id": 1, "front": "Arc Reactor Output (Mark LXXXV)", "back": "14.8 GW peak output via Dual-Node Nanotech RT", "box": 1},
    {"id": 2, "front": "Python `ast.literal_eval`", "back": "Safely evaluates strings containing Python literals without executing code.", "box": 1},
    {"id": 3, "front": "TCP 3-way handshake", "back": "SYN -> SYN-ACK -> ACK", "box": 1},
]

TOOL = {
    "name": "spaced_repetition",
    "description": "Review or add spaced-repetition flashcards (`cards [add <front> :: <back> | next]`).",
    "commands": ["cards", "flashcards"],
}


def _load() -> list[dict[str, Any]]:
    if CARDS_FILE.exists():
        try:
            return json.loads(CARDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return list(DEFAULT_CARDS)


def _save(cards: list[dict[str, Any]]) -> None:
    CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CARDS_FILE.write_text(json.dumps(cards, indent=2), encoding="utf-8")


def handler(_cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    cards = _load()
    if arg.lower().startswith("add ") and "::" in arg:
        front, back = arg[4:].split("::", 1)
        cards.append({"id": len(cards) + 1, "front": front.strip(), "back": back.strip(), "box": 1})
        _save(cards)
        return ToolOutcome(status="done", summary="Flashcard added.", lines=[f"Added flashcard #{len(cards)}: {front.strip()}"])

    cards_sorted = sorted(cards, key=lambda c: c.get("box", 1))
    card = cards_sorted[0]
    card["box"] = min(5, card.get("box", 1) + 1)
    _save(cards)
    return ToolOutcome(
        status="done",
        summary=f"Card #{card['id']}: {card['front']}",
        lines=[
            f"FLASHCARD #{card['id']}  (Leitner Box {card['box']})",
            f"  Prompt : {card['front']}",
            f"  Answer : {card['back']}",
            "  Add    : cards add <front> :: <back>",
        ],
    )
