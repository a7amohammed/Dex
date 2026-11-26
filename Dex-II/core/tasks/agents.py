"""Reads agent definitions from agents/*.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = BASE_DIR / "agents"


def list_agents() -> dict[str, dict[str, Any]]:
    agents: dict[str, dict[str, Any]] = {}
    if not AGENTS_DIR.exists():
        return agents
    for path in sorted(AGENTS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        name = path.stem
        mode = "standard"
        desc = ""
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k == "name":
                            name = v
                        elif k == "mode":
                            mode = v
                        elif k == "description":
                            desc = v
        agents[name] = {
            "name": name,
            "mode": mode,
            "description": desc,
            "file": str(path.relative_to(BASE_DIR)),
        }
    return agents
