"""Terminal engineering & physics quiz plugin."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome

BASE_DIR = Path(__file__).resolve().parent.parent
QUIZ_FILE = BASE_DIR / "memory" / ".quiz_state.json"

QUESTIONS = [
    {"q": "Which Python built-in module safely parses expression trees without executing arbitrary code?", "a": "ast", "hint": "Abstract Syntax Trees"},
    {"q": "What element powered Tony Stark's original chest Arc Reactor before Mark IV?", "a": "palladium", "hint": "Atomic number 46"},
    {"q": "In HTTP/REST, which status code indicates a resource was successfully created?", "a": "201", "hint": "2xx series"},
    {"q": "What is the time complexity of binary search on a sorted array of size n?", "a": "o(log n)", "hint": "Logarithmic"},
    {"q": "Which standard Python module measures disk capacity (`disk_usage`)?", "a": "shutil", "hint": "Shell utilities"},
]

TOOL = {
    "name": "quiz",
    "description": "Quick interactive STEM & engineering quiz (`quiz` or `quiz answer <text>`).",
    "commands": ["quiz"],
}


def handler(_cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    state = {}
    if QUIZ_FILE.exists():
        try:
            state = json.loads(QUIZ_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    if arg.lower().startswith("answer "):
        ans = arg[7:].strip().lower()
        current = state.get("current")
        if not current:
            return ToolOutcome(status="failed", summary="No active question. Run `quiz` first.")
        correct = current["a"]
        if ans == correct or correct in ans:
            state["score"] = state.get("score", 0) + 1
            state["current"] = None
            QUIZ_FILE.write_text(json.dumps(state), encoding="utf-8")
            return ToolOutcome(status="done", summary="Correct!", lines=[f"Correct, sir! Score: {state['score']}. Run `quiz` for the next question."])
        return ToolOutcome(status="done", summary="Incorrect.", lines=[f"Not quite — hint: {current['hint']}. Try again with `quiz answer <guess>`."])

    item = random.choice(QUESTIONS)
    state["current"] = item
    QUIZ_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUIZ_FILE.write_text(json.dumps(state), encoding="utf-8")
    return ToolOutcome(
        status="done",
        summary=item["q"],
        lines=[
            "J.A.R.V.I.S. QUIZ CHALLENGE",
            f"  Q: {item['q']}",
            "  Reply with: quiz answer <your answer>",
        ],
    )
