"""Plugin engine — AST validation, permission gate, enable/disable, dependency check, and crash isolation."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

from core.lazyimport import is_available
from memory.config_manager import load_settings, save_settings

BASE_DIR = Path(__file__).resolve().parent.parent
PLUGINS_DIR = BASE_DIR / "plugins"

BUILTIN_TRUSTED_PLUGINS = {
    "code_helper.py",
    "pomodoro.py",
    "quiz.py",
    "shopping_list.py",
    "spaced_repetition.py",
    "water_reminder.py",
}

SENSITIVE_IMPORTS = {"subprocess", "socket", "ctypes", "pty", "shutil", "urllib", "http", "ftplib"}
SENSITIVE_CALLS = {"eval", "exec", "compile", "system", "popen", "Popen"}


def validate_plugin_ast(path: Path) -> dict[str, Any]:
    """Inspect plugin AST without executing module code."""
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return {"valid": False, "error": f"SyntaxError line {exc.lineno}: {exc.msg}", "risky": [], "dependencies": [], "has_tool": False, "has_handler": False}

    has_tool = False
    has_handler = False
    dependencies: list[str] = []
    risky: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "TOOL":
                        has_tool = True
                    elif target.id == "DEPENDENCIES" and isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                dependencies.append(elt.value)
        elif isinstance(node, ast.FunctionDef) and node.name == "handler":
            has_handler = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in SENSITIVE_IMPORTS:
                    risky.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root_pkg = node.module.split(".")[0]
            if root_pkg in SENSITIVE_IMPORTS:
                risky.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in SENSITIVE_CALLS:
                risky.append(f"{node.func.id}()")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in SENSITIVE_CALLS:
                risky.append(f".{node.func.attr}()")

    return {
        "valid": has_tool and has_handler,
        "error": None if (has_tool and has_handler) else "Missing required TOOL dict or handler() function.",
        "risky": sorted(set(risky)),
        "dependencies": dependencies,
        "has_tool": has_tool,
        "has_handler": has_handler,
    }


def inspect_all_plugins() -> list[dict[str, Any]]:
    """Return full status records for all plugins/*.py files (including disabled/quarantined/errors)."""
    settings = load_settings()
    disabled = set(settings.get("disabled_plugins", []))
    approved = set(settings.get("approved_plugins", []))
    records: list[dict[str, Any]] = []

    if not PLUGINS_DIR.exists():
        return records

    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        stem = path.stem
        audit = validate_plugin_ast(path)
        missing_deps = [d for d in audit["dependencies"] if not is_available(d)]
        trusted = path.name in BUILTIN_TRUSTED_PLUGINS or stem in approved or path.name in approved

        record: dict[str, Any] = {
            "name": stem,
            "file": f"plugins/{path.name}",
            "filename": path.name,
            "description": "",
            "commands": [],
            "dependencies": audit["dependencies"],
            "missing_dependencies": missing_deps,
            "risky_patterns": audit["risky"],
            "trusted": trusted,
            "enabled": stem not in disabled and path.name not in disabled,
            "status": "unknown",
            "error": audit["error"],
            "tool": None,
            "handler": None,
        }

        if not audit["valid"]:
            record["status"] = "error"
            records.append(record)
            continue

        if not record["enabled"]:
            record["status"] = "disabled"
            records.append(record)
            continue

        if audit["risky"] and not trusted:
            record["status"] = "quarantined"
            record["error"] = f"Requires approval before execution ({', '.join(audit['risky'])})"
            records.append(record)
            continue

        if missing_deps:
            record["status"] = "missing_dep"
            record["error"] = f"Missing dependencies: {', '.join(missing_deps)}"
            records.append(record)
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{stem}", path)
            if not spec or not spec.loader:
                record["status"] = "error"
                record["error"] = "Unable to create module loader spec."
                records.append(record)
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tool = getattr(mod, "TOOL", None)
            handler = getattr(mod, "handler", None)
            if isinstance(tool, dict) and callable(handler) and "name" in tool:
                record["name"] = tool["name"]
                record["description"] = tool.get("description", "")
                record["commands"] = list(tool.get("commands", [tool["name"]]))
                record["status"] = "active"
                record["tool"] = tool
                record["handler"] = handler
            else:
                record["status"] = "error"
                record["error"] = "Invalid TOOL/handler contract."
        except Exception as exc:
            record["status"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"

        records.append(record)

    return records


def discover_plugins() -> tuple[dict[str, dict[str, Any]], list[str]]:
    plugins: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for rec in inspect_all_plugins():
        if rec["status"] == "active":
            plugins[rec["name"]] = rec
        elif rec["status"] in ("error", "quarantined", "missing_dep") and rec["error"]:
            errors.append(f"{rec['filename']}: {rec['error']}")
    return plugins, errors


def toggle_plugin(name_or_filename: str) -> tuple[bool, str]:
    settings = load_settings()
    disabled: list[str] = list(settings.get("disabled_plugins", []))
    key = name_or_filename.replace("plugins/", "").replace(".py", "").strip()
    if key in disabled:
        disabled.remove(key)
        settings["disabled_plugins"] = disabled
        save_settings(settings)
        return True, f"Enabled plugin '{key}'."
    disabled.append(key)
    settings["disabled_plugins"] = disabled
    save_settings(settings)
    return False, f"Disabled plugin '{key}'."


def approve_plugin(name_or_filename: str) -> str:
    settings = load_settings()
    approved: list[str] = list(settings.get("approved_plugins", []))
    key = name_or_filename.replace("plugins/", "").replace(".py", "").strip()
    if key not in approved:
        approved.append(key)
        settings["approved_plugins"] = approved
        save_settings(settings)
    return f"Approved plugin '{key}' for execution."
