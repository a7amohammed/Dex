"""Read-only workspace file inspection with strict path-traversal guard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome, wrap_untrusted

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = BASE_DIR.parent

TOOL = {
    "name": "file_controller",
    "description": "Scan workspace files or preview a file safely within the project directory.",
    "commands": ["scan", "cat", "read"],
}


def _safe_resolve(rel: str) -> Path | None:
    target = (WORKSPACE_ROOT / rel).resolve() if rel else WORKSPACE_ROOT
    if WORKSPACE_ROOT not in target.parents and target != WORKSPACE_ROOT:
        return None
    return target


def handler(cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    if cmd in ("cat", "read"):
        if not arg:
            return ToolOutcome(status="failed", summary="Usage: read <relative_path>")
        target = _safe_resolve(arg)
        if not target or not target.exists() or not target.is_file():
            return ToolOutcome(status="failed", summary=f"File not accessible: {arg}")
        text = target.read_text(encoding="utf-8", errors="replace")[:4000]
        wrapped = wrap_untrusted(arg, text)
        return ToolOutcome(
            status="done",
            summary=f"Read {arg}",
            lines=[f"FILE PREVIEW  ·  {arg}", "------------------------------------------------------------------------", *text.splitlines()[:60]],
            data={"wrapped": wrapped},
            untrusted_source=arg,
        )

    target = _safe_resolve(arg)
    if not target:
        return ToolOutcome(status="failed", summary="Access denied: path resolves outside workspace boundary.")
    if not target.exists():
        return ToolOutcome(status="failed", summary=f"Path not found: {arg}")

    ignore_dirs = {"node_modules", ".git", "dist", "__pycache__", ".venv"}
    entries: list[tuple[str, int]] = []
    ext_counts: dict[str, int] = {}
    total_bytes = 0

    if target.is_file():
        sz = target.stat().st_size
        rel = str(target.relative_to(WORKSPACE_ROOT))
        return ToolOutcome(
            status="done",
            summary=f"File {rel} ({sz} bytes)",
            lines=[f"  {sz:>8,} B   {rel}"],
        )

    for root, dirs, files in os.walk(target):
        dirs[:] = sorted([d for d in dirs if d not in ignore_dirs])
        for fname in sorted(files):
            fp = Path(root) / fname
            try:
                sz = fp.stat().st_size
            except OSError:
                sz = 0
            ext = fp.suffix or "no_ext"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            total_bytes += sz
            if len(entries) < 30:
                entries.append((str(fp.relative_to(WORKSPACE_ROOT)), sz))

    root_label = "." if target == WORKSPACE_ROOT else str(target.relative_to(WORKSPACE_ROOT))
    ext_summary = ", ".join(f"{k} ({v})" for k, v in sorted(ext_counts.items(), key=lambda kv: kv[1], reverse=True)[:8])
    lines = [
        f"WORKSPACE SCAN  ·  Root: {root_label}",
        "------------------------------------------------------------------------",
        f"  Total Files : {sum(ext_counts.values())}   Total Size : {total_bytes:,} bytes",
        f"  Extensions  : {ext_summary}",
        "",
        *[f"  {sz:>8,} B   {rel}" for rel, sz in entries],
    ]
    if sum(ext_counts.values()) > 30:
        lines.append(f"  ... ({sum(ext_counts.values()) - 30} additional files omitted)")
    return ToolOutcome(status="done", summary=f"Scanned {sum(ext_counts.values())} files.", lines=lines)
