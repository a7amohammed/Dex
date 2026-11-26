"""Irreversible-action confirmation gate.

Tokens are issued by the terminal runtime — never invented by the LLM — and expire quickly.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIRM_FILE = BASE_DIR / "memory" / ".pending_confirm.json"
TOKEN_TTL_SECONDS = 120


def _load_pending() -> dict[str, Any]:
    if CONFIRM_FILE.exists():
        try:
            data = json.loads(CONFIRM_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_pending(data: dict[str, Any]) -> None:
    CONFIRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIRM_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def issue_confirmation(action_id: str, description: str, payload: dict[str, Any] | None = None) -> str:
    token = secrets.token_hex(3).upper()
    pending = _load_pending()
    now = time.time()
    # Prune expired
    pending = {k: v for k, v in pending.items() if now - v.get("created", 0) < TOKEN_TTL_SECONDS}
    pending[token] = {
        "action_id": action_id,
        "description": description,
        "payload": payload or {},
        "created": now,
    }
    _save_pending(pending)
    return token


def consume_confirmation(token: str) -> dict[str, Any] | None:
    clean = token.strip().upper()
    pending = _load_pending()
    entry = pending.pop(clean, None)
    _save_pending(pending)
    if not entry:
        return None
    if time.time() - entry.get("created", 0) > TOKEN_TTL_SECONDS:
        return None
    return entry
