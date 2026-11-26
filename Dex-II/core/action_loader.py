"""Bundled action engine — discovers, inspects, and toggles actions/*.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from memory.config_manager import load_settings, save_settings

BASE_DIR = Path(__file__).resolve().parent.parent
ACTIONS_DIR = BASE_DIR / "actions"


def inspect_all_actions() -> list[dict[str, Any]]:
    settings = load_settings()
    disabled = set(settings.get("disabled_actions", []))
    records: list[dict[str, Any]] = []

    if not ACTIONS_DIR.exists():
        return records

    for path in sorted(ACTIONS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        stem = path.stem
        enabled = stem not in disabled and path.name not in disabled
        rec: dict[str, Any] = {
            "name": stem,
            "file": f"actions/{path.name}",
            "filename": path.name,
            "description": "",
            "commands": [],
            "enabled": enabled,
            "status": "disabled" if not enabled else "unknown",
            "error": None,
            "tool": None,
            "handler": None,
        }
        if not enabled:
            records.append(rec)
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"actions.{stem}", path)
            if not spec or not spec.loader:
                rec["status"] = "error"
                rec["error"] = "Unable to create module spec."
                records.append(rec)
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tool = getattr(mod, "TOOL", None)
            handler = getattr(mod, "handler", None)
            if isinstance(tool, dict) and callable(handler) and "name" in tool:
                rec["name"] = tool["name"]
                rec["description"] = tool.get("description", "")
                rec["commands"] = list(tool.get("commands", [tool["name"]]))
                rec["status"] = "active"
                rec["tool"] = tool
                rec["handler"] = handler
            else:
                rec["status"] = "error"
                rec["error"] = "Missing TOOL dict or handler()."
        except Exception as exc:
            rec["status"] = "error"
            rec["error"] = f"{type(exc).__name__}: {exc}"
        records.append(rec)

    return records


def discover_actions() -> tuple[dict[str, dict[str, Any]], list[str]]:
    actions: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for rec in inspect_all_actions():
        if rec["status"] == "active":
            actions[rec["name"]] = rec
        elif rec["status"] == "error" and rec["error"]:
            errors.append(f"{rec['filename']}: {rec['error']}")
    return actions, errors


def toggle_action(name_or_filename: str) -> tuple[bool, str]:
    settings = load_settings()
    disabled: list[str] = list(settings.get("disabled_actions", []))
    key = name_or_filename.replace("actions/", "").replace(".py", "").strip()
    if key in disabled:
        disabled.remove(key)
        settings["disabled_actions"] = disabled
        save_settings(settings)
        return True, f"Enabled action '{key}'."
    disabled.append(key)
    settings["disabled_actions"] = disabled
    save_settings(settings)
    return False, f"Disabled action '{key}'."
