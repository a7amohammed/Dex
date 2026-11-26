"""Atomic JSON store for Mark LVII background tasks."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = BASE_DIR / "memory" / "tasks"


def ensure_dirs() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "reports").mkdir(parents=True, exist_ok=True)


def save_task(task: dict[str, Any]) -> None:
    ensure_dirs()
    target = TASKS_DIR / f"{task['id']}.json"
    fd, tmp_name = tempfile.mkstemp(dir=str(TASKS_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(task, fh, indent=2)
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def load_task(task_id: str) -> dict[str, Any] | None:
    path = TASKS_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_tasks() -> list[dict[str, Any]]:
    ensure_dirs()
    tasks: list[dict[str, Any]] = []
    for path in sorted(TASKS_DIR.glob("*.json"), reverse=True):
        try:
            tasks.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return tasks
