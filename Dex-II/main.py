#!/usr/bin/env python3
"""
DEX // Mark LVII — AURA TERMINAL Core
Modular Terminal Architecture (Python 3.10+ standard library)

Interactive AURA Terminal TUI:
    python3 main.py

Line-by-line CLI REPL:
    python3 main.py --cli

Single-command structured JSON bridge:
    python3 main.py --exec "status" --json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

# Ensure Dex-II/ is on sys.path regardless of caller CWD
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from actions.system_monitor import collect_snapshot, make_bar
from core.action_loader import discover_actions, inspect_all_actions, toggle_action
from core.audio_devices import list_audio_devices
from core.confirm import consume_confirmation
from core.gemini import generate_chat_reply
from core.outcome import ToolOutcome
from core.platform_support import detect_platform_support
from core.plugin_loader import approve_plugin, discover_plugins, inspect_all_plugins, toggle_plugin
from core.routines.engine import RoutineScheduler, load_routines
from core.tasks.agents import list_agents
from core.tasks.engine import get_tasks_summary
from core.undo import list_undo, pop_and_undo, push_undo, register_undo_handler
from memory.config_manager import (
    MARK_SUITS,
    THEMES,
    export_config_backup,
    list_config_backups,
    load_settings,
    restore_config_backup,
    save_settings,
)
from memory.memory_manager import clear_memory_facts, load_memory
from providers.registry import provider_availability_report

CYAN = "\033[38;2;0;240;255m"
BLUE = "\033[38;2;56;189;248m"
PURPLE = "\033[38;2;168;85;247m"
GREEN = "\033[38;2;16;185;129m"
RED = "\033[38;2;239;68;68m"
SLATE = "\033[38;2;148;163;184m"
WHITE = "\033[38;2;241;245;249m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

PROTOCOLS: dict[str, dict[str, Any]] = {
    "house_party": {
        "title": "HOUSE PARTY PROTOCOL",
        "summary": "All Iron Legion autonomous suits mobilized for perimeter defense.",
        "status": "ACTIVE — IRON LEGION DEPLOYED",
        "subsystems": {"reactor": 100, "repulsors": 95, "thrusters": 92, "shielding": 90, "sensors": 100},
    },
    "clean_slate": {
        "title": "CLEAN SLATE PROTOCOL",
        "summary": "Initiating controlled non-combat telemetry reset to baseline standby.",
        "status": "STANDBY — BASELINE RESTORED",
        "subsystems": {"reactor": 75, "repulsors": 50, "thrusters": 50, "shielding": 60, "sensors": 80},
    },
    "veronica": {
        "title": "VERONICA ORBITAL DEPLOYMENT",
        "summary": "Hulkbuster orbital module locked on low-Earth trajectory.",
        "status": "ACTIVE — ORBITAL POD ARMED",
        "subsystems": {"reactor": 100, "repulsors": 98, "thrusters": 86, "shielding": 100, "sensors": 95},
    },
    "barn_door": {
        "title": "BARN DOOR LOCKDOWN",
        "summary": "Perimeter blast doors sealed. External comms routed through encrypted relay.",
        "status": "LOCKED — PERIMETER SECURED",
        "subsystems": {"reactor": 88, "repulsors": 40, "thrusters": 20, "shielding": 100, "sensors": 100},
    },
    "overdrive": {
        "title": "OVERDRIVE REACTOR SURGE",
        "summary": "Diverting auxiliary thermal headroom to repulsor and thruster manifolds.",
        "status": "SURGE — PEAK OUTPUT",
        "subsystems": {"reactor": 100, "repulsors": 100, "thrusters": 100, "shielding": 84, "sensors": 92},
    },
}

ARC_REACTOR_ASCII = [
    "          . - ~ ~ ~ - .          ",
    "      . '   /  | |  \\   ' .      ",
    "    /     /  _.-+-._  \\     \\    ",
    "   /    /  .'  / \\  '.  \\    \\   ",
    "  |    |  /   /   \\   \\  |    |  ",
    "  |----+--|  (  O  )  |--+----|  ",
    "  |    |  \\   \\   /   /  |    |  ",
    "   \\    \\  '.  \\_/  .'  /    /   ",
    "    \\     \\  '-+-+-'  /     /    ",
    "      ' .   \\  | |  /   . '      ",
    "          ' - ~ ~ ~ - '          ",
]


def _undo_suit(payload: dict[str, Any]) -> str:
    prev = payload.get("previous_suit")
    if prev and prev in MARK_SUITS:
        s = load_settings()
        s["active_suit"] = prev
        save_settings(s)
        return f"Restored {MARK_SUITS[prev]['designation']}."
    return "No previous suit recorded."


register_undo_handler("switch_suit", _undo_suit)


def _strip_callable_meta(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": rec.get("name", ""),
        "description": rec.get("description", ""),
        "commands": list(rec.get("commands", [])),
        "file": rec.get("file", ""),
        "filename": rec.get("filename", ""),
        "enabled": bool(rec.get("enabled", True)),
        "status": rec.get("status", "unknown"),
        "error": rec.get("error"),
        "dependencies": list(rec.get("dependencies", [])),
        "missing_dependencies": list(rec.get("missing_dependencies", [])),
        "risky_patterns": list(rec.get("risky_patterns", [])),
        "trusted": bool(rec.get("trusted", True)),
    }


def render_system_prompt(actions_count: int, plugins_count: int) -> str:
    template_path = BASE_DIR / "core" / "prompt.txt"
    raw = template_path.read_text(encoding="utf-8") if template_path.exists() else "You are {assistant_name}."
    settings = load_settings()
    plat = detect_platform_support()
    t = collect_snapshot()
    tasks = get_tasks_summary()
    routines = load_routines()
    mem = load_memory()
    return raw.format(
        assistant_name=settings.get("assistant_name", "DEX"),
        suit_designation=t["suit"]["designation"],
        suit_codename=t["suit"]["codename"],
        protocol=t["protocol"],
        os_name=t["system"]["os"],
        distro_name=plat["distro"].get("pretty_name", t["system"]["os"]),
        arch=t["system"]["arch"],
        python_version=t["python"]["version"],
        cpu_pct=t["cpu"]["utilization_pct"],
        cpu_cores=t["cpu"]["cores"],
        mem_pct=t["memory"]["percent"],
        mem_used=t["memory"]["used_gb"],
        mem_total=t["memory"]["total_gb"],
        actions_count=actions_count,
        plugins_count=plugins_count,
        tasks_active=len([x for x in tasks if x.get("status") != "cancelled"]),
        routines_count=len(routines),
        facts_count=len(mem.get("facts", [])),
    )


def build_architecture_snapshot() -> dict[str, Any]:
    all_actions = inspect_all_actions()
    all_plugins = inspect_all_plugins()
    active_actions = [_strip_callable_meta(a) for a in all_actions if a.get("status") == "active"]
    active_plugins = [_strip_callable_meta(p) for p in all_plugins if p.get("status") == "active"]
    errors = [
        f"{m['filename']}: {m['error']}"
        for m in [*all_actions, *all_plugins]
        if m.get("status") in ("error", "quarantined", "missing_dep") and m.get("error")
    ]
    from providers.wakeword_oww import OpenWakeWordProvider

    agents = list_agents()
    mem = load_memory()
    s = load_settings()
    ww_cfg = s.get("wakeword", {})
    ww_detail = OpenWakeWordProvider(
        phrase=str(ww_cfg.get("phrase", "hey dex")),
        model_path=str(ww_cfg.get("model_path", "providers/wakewords/hey_dex.onnx")),
        threshold=float(ww_cfg.get("threshold", 0.5)),
        cooldown_s=float(ww_cfg.get("cooldown_s", 2.0)),
        inference_framework=str(ww_cfg.get("inference_framework", "onnx")),
    ).availability_detail()
    ww_detail["enabled"] = bool(ww_cfg.get("enabled", False))
    return {
        "actions": active_actions,
        "plugins": active_plugins,
        "all_actions": [_strip_callable_meta(a) for a in all_actions],
        "all_plugins": [_strip_callable_meta(p) for p in all_plugins],
        "agents": list(agents.values()),
        "tasks": get_tasks_summary()[:20],
        "routines": load_routines(),
        "providers": provider_availability_report(),
        "audio_devices": list_audio_devices(),
        "wakeword": ww_detail,
        "memory_summary": {
            "facts_count": len(mem.get("facts", [])),
            "sessions_count": len(mem.get("sessions", [])),
        },
        "undo_depth": len(list_undo()),
        "platform": detect_platform_support(),
        "errors": errors,
    }


def _active_tool_registry() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    actions, _ = discover_actions()
    plugins, _ = discover_plugins()
    combined: dict[str, dict[str, Any]] = {}
    combined.update(actions)
    combined.update(plugins)
    return actions, plugins, combined


def dispatch_command(raw_input: str) -> dict[str, Any]:
    text = raw_input.strip()
    if not text:
        return {"mode": "local", "kind": "info", "lines": []}

    actions, plugins, combined_tools = _active_tool_registry()

    cmd_map: dict[str, dict[str, Any]] = {}
    for entry in combined_tools.values():
        for alias in entry.get("commands", []):
            cmd_map[alias.lower()] = entry

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("help", "?"):
        lines = [
            "DEX // MARK LVII — AURA TERMINAL COMMAND MATRIX",
            "------------------------------------------------------------------------",
            "CORE & ARMOR",
            "  status | sysinfo          Real-time CPU, RAM, disk, Python & suit telemetry",
            "  diag | diagnostics        Multi-stage hardware & reactor integrity sweep",
            "  suit [mark3..mark85]      Inspect or deploy Mark armor (supports `undo`)",
            "  power <subsys> <0-100>    Route power (reactor/repulsors/thrusters/shielding/sensors)",
            "  protocol <name>           Run house_party, clean_slate, veronica, barn_door, overdrive",
            "",
            "ENGINE, PLUGINS, ACTIONS & MEMORY",
            "  task <start|research|list|check|steer|resume|cancel>  Background agent tasks",
            "  routine <add|list|run|remove|quiet>            Scheduled routines & quiet hours",
            "  remember <fact> | memory | forget <id|all>     Long-term memory (confirm-gated clear)",
            "  plugin <list|enable|disable|approve|reload>    Manage drop-in plugins",
            "  action <list|enable|disable|reload>            Manage bundled actions",
            "  wakeword <status|enable|disable|threshold <n>> Configure openWakeWord ('hey dex')",
            "  settings | backup [label] | restore <file>     Inspect settings or backup/restore",
            "  note <add|list|clear>                          Persistent mission log",
            "  undo | confirm <TOKEN>                         Revert or authorize gated command",
            "  actions | plugins | platform | test providers  Inspect modular architecture",
            "",
            "DROP-IN PLUGINS",
            "  py <code> | calc <expr>   Sandboxed Python interpreter & AST calculator",
            "  scan [dir] | read <file>  Workspace scanner & guarded file preview",
            "  pomodoro [start|status]   Deep-work Pomodoro timer",
            "  shop <add|list|done>      Persistent shopping list",
            "  water <log|status>        Daily hydration tracker",
            "  quiz | cards              Engineering quiz & spaced-repetition flashcards",
            "  <any natural query>       Consult DEX AI with multi-turn tool calling",
        ]
        return {"mode": "local", "kind": "help", "lines": lines}

    if cmd == "plugin":
        sub = arg.split(maxsplit=1)
        action = sub[0].lower() if sub else "list"
        target = sub[1].strip() if len(sub) > 1 else ""
        if action in ("list", "inspect", "reload"):
            records = inspect_all_plugins()
            lines = [f"DROP-IN PLUGINS ({len(records)} discovered)"]
            for r in records:
                cmds = ", ".join(r["commands"]) or "-"
                lines.append(f"  [{r['status'].upper():<11}] {r['name']:<18} [{cmds}]  {r['file']}")
                if r.get("error"):
                    lines.append(f"      ! {r['error']}")
            return {"mode": "local", "kind": "info", "lines": lines}
        if action in ("enable", "disable", "toggle") and target:
            records = inspect_all_plugins()
            match = next((r for r in records if target in (r["name"], r["filename"], Path(r["filename"]).stem)), None)
            if not match:
                return {"mode": "local", "kind": "error", "lines": [f"Unknown plugin '{target}'."]}
            key = Path(match["filename"]).stem
            if action == "enable" and match["enabled"]:
                return {"mode": "local", "kind": "info", "lines": [f"Plugin '{key}' is already enabled."]}
            if action == "disable" and not match["enabled"]:
                return {"mode": "local", "kind": "info", "lines": [f"Plugin '{key}' is already disabled."]}
            _enabled, msg = toggle_plugin(key)
            return {"mode": "local", "kind": "info", "lines": [msg]}
        if action == "approve" and target:
            msg = approve_plugin(target)
            return {"mode": "local", "kind": "info", "lines": [msg]}
        return {"mode": "local", "kind": "error", "lines": ["Usage: plugin <list|enable|disable|toggle|approve|reload> [name]"]}

    if cmd == "action":
        sub = arg.split(maxsplit=1)
        subcmd = sub[0].lower() if sub else "list"
        target = sub[1].strip() if len(sub) > 1 else ""
        if subcmd in ("list", "inspect", "reload"):
            records = inspect_all_actions()
            lines = [f"BUNDLED ACTIONS ({len(records)} discovered)"]
            for r in records:
                cmds = ", ".join(r["commands"]) or "-"
                lines.append(f"  [{r['status'].upper():<11}] {r['name']:<18} [{cmds}]  {r['file']}")
                if r.get("error"):
                    lines.append(f"      ! {r['error']}")
            return {"mode": "local", "kind": "info", "lines": lines}
        if subcmd in ("enable", "disable", "toggle") and target:
            records = inspect_all_actions()
            match = next((r for r in records if target in (r["name"], r["filename"], Path(r["filename"]).stem)), None)
            if not match:
                return {"mode": "local", "kind": "error", "lines": [f"Unknown action '{target}'."]}
            key = Path(match["filename"]).stem
            if subcmd == "enable" and match["enabled"]:
                return {"mode": "local", "kind": "info", "lines": [f"Action '{key}' is already enabled."]}
            if subcmd == "disable" and not match["enabled"]:
                return {"mode": "local", "kind": "info", "lines": [f"Action '{key}' is already disabled."]}
            _enabled, msg = toggle_action(key)
            return {"mode": "local", "kind": "info", "lines": [msg]}
        return {"mode": "local", "kind": "error", "lines": ["Usage: action <list|enable|disable|toggle|reload> [name]"]}

    if cmd == "wakeword":
        from providers.wakeword_oww import OpenWakeWordProvider

        sub = arg.split(maxsplit=1)
        subcmd = sub[0].lower() if sub else "status"
        val = sub[1].strip() if len(sub) > 1 else ""
        s = load_settings()
        ww = s.setdefault("wakeword", {})

        if subcmd in ("enable", "on"):
            ww["enabled"] = True
            save_settings(s)
        elif subcmd in ("disable", "off"):
            ww["enabled"] = False
            save_settings(s)
        elif subcmd == "toggle":
            ww["enabled"] = not bool(ww.get("enabled", False))
            save_settings(s)
        elif subcmd == "threshold" and val:
            try:
                ww["threshold"] = max(0.1, min(0.95, float(val)))
                save_settings(s)
            except ValueError:
                return {"mode": "local", "kind": "error", "lines": ["Threshold must be a float between 0.1 and 0.95."]}
        elif subcmd == "phrase" and val:
            ww["phrase"] = val.strip()
            save_settings(s)
        elif subcmd not in ("status", "check"):
            return {"mode": "local", "kind": "error", "lines": ["Usage: wakeword <status|enable|disable|toggle|threshold <0.1-0.95>|phrase <text>>"]}

        detail = OpenWakeWordProvider(
            phrase=str(ww.get("phrase", "hey dex")),
            model_path=str(ww.get("model_path", "providers/wakewords/hey_dex.onnx")),
            threshold=float(ww.get("threshold", 0.5)),
            cooldown_s=float(ww.get("cooldown_s", 2.0)),
            inference_framework=str(ww.get("inference_framework", "onnx")),
        ).availability_detail()
        lines = [
            "OPENWAKEWORD // 'HEY DEX' STATUS",
            "------------------------------------------------------------------------",
            f"  Enabled     : {ww.get('enabled', False)}   Phrase: '{detail['phrase']}'",
            f"  Threshold   : {detail['threshold']:.2f}   Model: {detail['model_path']}",
            f"  Ready       : {detail['ready']}   Reason: {detail['reason']}",
        ]
        return {"mode": "local", "kind": "info", "lines": lines}

    if cmd == "settings":
        s = load_settings()
        theme_label = THEMES.get(s.get("theme", "cyberpunk_aura"), {}).get("label", s.get("theme"))
        ww = s.get("wakeword", {})
        lines = [
            "DEX // AURA TERMINAL SETTINGS",
            "------------------------------------------------------------------------",
            f"  Assistant     : {s.get('assistant_name', 'DEX')}   Suit: {s.get('active_suit')}",
            f"  Theme         : {theme_label}   Density: {s['layout']['density']}",
            f"  Animations    : {s['animations']['enabled']}   Waveform Bars: {s['animations']['waveform_bars']}",
            f"  Audio I/O     : in={s['audio']['input_device']}  out={s['audio']['output_device']}  gain={s['audio']['mic_gain']:.1f}x",
            f"  Voice         : stt={s['voice']['stt_provider']}  tts={s['voice']['tts_provider']} ({s['voice']['voice_name']})",
            f"  Wake Word     : enabled={ww.get('enabled', False)}  phrase='{ww.get('phrase', 'hey dex')}'  threshold={ww.get('threshold', 0.5):.2f}",
            f"  AI Provider   : {s['ai']['provider']} ({s['ai']['gemini_model']} / {s['ai']['openai_model']})",
            f"  Shortcuts     : settings=[{s['shortcuts']['settings'].upper()}]  voice={s['shortcuts']['voice_primary']} / {s['shortcuts']['voice_fallback']}",
            f"  Performance   : tick={s['performance']['tick_ms']}ms  scheduler={s['performance']['background_scheduler']}",
        ]
        return {"mode": "local", "kind": "info", "lines": lines}

    if cmd == "backup":
        path = export_config_backup(arg or "manual")
        return {"mode": "local", "kind": "info", "lines": [f"Configuration backup saved to {path.name}."]}

    if cmd == "restore":
        backups = list_config_backups()
        if not arg:
            if not backups:
                return {"mode": "local", "kind": "info", "lines": ["No configuration backups found in config/backups/."]}
            lines = ["AVAILABLE CONFIGURATION BACKUPS"]
            for i, b in enumerate(backups[:10], start=1):
                lines.append(f"  {i}. {b.name}")
            lines.append("Usage: restore <index|filename>")
            return {"mode": "local", "kind": "info", "lines": lines}
        target_path: Path | None = None
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(backups):
                target_path = backups[idx]
        else:
            target_path = next((b for b in backups if b.name == arg or arg in b.name), None)
        if not target_path or not restore_config_backup(target_path):
            return {"mode": "local", "kind": "error", "lines": [f"Could not restore backup '{arg}'."]}
        return {"mode": "local", "kind": "info", "lines": [f"Configuration restored from {target_path.name}."]}

    if cmd in ("actions", "plugins", "architecture"):
        snap = build_architecture_snapshot()
        lines = [
            "DEX // MARK LVII MODULAR ARCHITECTURE",
            "------------------------------------------------------------------------",
            f"  ACTIONS ({len(snap['actions'])} active / {len(snap['all_actions'])} total)",
            *[
                f"    - [{a['status'].upper():<8}] {a['name']:<18} [{', '.join(a['commands'])}]  {a['file']}"
                for a in snap["all_actions"]
            ],
            "",
            f"  PLUGINS ({len(snap['plugins'])} active / {len(snap['all_plugins'])} total)",
            *[
                f"    - [{p['status'].upper():<8}] {p['name']:<18} [{', '.join(p['commands'])}]  {p['file']}"
                for p in snap["all_plugins"]
            ],
            "",
            f"  AGENTS ({len(snap['agents'])}) · ROUTINES ({len(snap['routines'])}) · UNDO STACK ({snap['undo_depth']})",
        ]
        if snap["errors"]:
            lines.extend(["", "  ISOLATED / QUARANTINED MODULES:", *[f"    ! {e}" for e in snap["errors"]]])
        return {"mode": "local", "kind": "info", "lines": lines, "architecture": snap}

    if cmd == "platform":
        plat = detect_platform_support()
        audio = plat["audio"]
        lines = [
            "PLATFORM CAPABILITY REPORT",
            "------------------------------------------------------------------------",
            f"  OS / Distro : {plat['os']} {plat['release']} ({plat['arch']}) — {plat['distro']['pretty_name']}",
            f"  Display     : {plat['display_server']}   Python: {plat['python_version']}   TTY: {plat['tty']}   ANSI: {plat['ansi_color']}",
            f"  Audio Stack : {audio['backend']} (Capture ready: {audio['voice_capture_ready']}, TTS ready: {audio['tts_ready']})",
            f"  Tools       : python3={plat['tools_available']['python3']}, git={plat['tools_available']['git']}, ffmpeg={plat['tools_available']['ffmpeg']}",
            f"  Notes       : {plat['notes']}",
        ]
        return {"mode": "local", "kind": "info", "lines": lines}

    if cmd == "test" and arg.lower() == "providers":
        from providers._tests import run_suite
        ok, output = run_suite()
        return {
            "mode": "local",
            "kind": "python" if ok else "error",
            "lines": output.strip().splitlines(),
        }

    if cmd == "undo":
        ok, msg = pop_and_undo()
        return {
            "mode": "local",
            "kind": "info" if ok else "error",
            "lines": [msg],
            "telemetry": collect_snapshot(),
        }

    if cmd == "confirm":
        if not arg:
            return {"mode": "local", "kind": "error", "lines": ["Usage: confirm <TOKEN>"]}
        gate = consume_confirmation(arg)
        if not gate:
            return {"mode": "local", "kind": "error", "lines": [f"Confirmation token '{arg}' is invalid or expired."]}
        if gate["action_id"] == "clear_memory":
            count = clear_memory_facts()
            return {
                "mode": "local",
                "kind": "note",
                "lines": [f"Confirmed. Erased {count} long-term memory entries."],
                "telemetry": collect_snapshot(),
            }
        return {"mode": "local", "kind": "info", "lines": [f"Confirmed action '{gate['action_id']}'."]}

    if cmd in ("suit", "mark"):
        settings = load_settings()
        if not arg:
            lines = ["AVAILABLE STARK ARMOR SUITS", "------------------------------------------------------------------------"]
            for key, s in MARK_SUITS.items():
                marker = "*" if key == settings["active_suit"] else " "
                lines.append(
                    f"  {marker} {key:<7} {s['designation']:<11} {s['codename']:<24} Mach {s['max_mach']:<4} {s['power_output_gw']} GW"
                )
            lines.append("")
            lines.append("Usage: suit <mark3|mark7|mark42|mark50|mark57|mark85>")
            return {"mode": "local", "kind": "suit", "lines": lines, "telemetry": collect_snapshot()}

        norm = arg.lower().replace(" ", "").replace("-", "")
        aliases = {
            "3": "mark3", "7": "mark7", "42": "mark42", "50": "mark50", "57": "mark57", "85": "mark85",
            "iii": "mark3", "vii": "mark7", "xlii": "mark42", "l": "mark50", "lvii": "mark57", "lxxxv": "mark85",
        }
        target_key = aliases.get(norm, norm)
        if target_key not in MARK_SUITS:
            return {"mode": "local", "kind": "error", "lines": [f"Unknown chassis '{arg}'. Available: {', '.join(MARK_SUITS.keys())}"]}
        prev_suit = settings["active_suit"]
        settings["active_suit"] = target_key
        save_settings(settings)
        push_undo("switch_suit", f"Switch suit from {prev_suit} to {target_key}", {"previous_suit": prev_suit})
        suit = MARK_SUITS[target_key]
        lines = [
            f"DEPLOYING {suit['designation'].upper()} — {suit['codename']}",
            f"  Power Core : {suit['core']} ({suit['power_output_gw']} GW)",
            f"  Top Speed  : Mach {suit['max_mach']}  ·  Integrity: {suit['armor_integrity']}%",
            f"  Briefing   : {suit['notes']}",
            f"All systems transferred to {suit['designation']}. (Type `undo` to revert.)",
        ]
        return {"mode": "local", "kind": "suit", "lines": lines, "telemetry": collect_snapshot()}

    if cmd == "power":
        sub_parts = arg.split()
        if len(sub_parts) != 2:
            return {"mode": "local", "kind": "error", "lines": ["Usage: power <reactor|repulsors|thrusters|shielding|sensors> <0-100>"]}
        subsys = sub_parts[0].lower()
        settings = load_settings()
        if subsys not in settings["subsystems"]:
            return {"mode": "local", "kind": "error", "lines": [f"Unknown subsystem '{subsys}'."]}
        try:
            val = max(0, min(100, int(sub_parts[1])))
        except ValueError:
            return {"mode": "local", "kind": "error", "lines": ["Power level must be an integer 0–100."]}
        settings["subsystems"][subsys] = val
        save_settings(settings)
        return {
            "mode": "local",
            "kind": "power",
            "lines": [f"Adjusted {subsys} allocation to {val}%  {make_bar(val)}"],
            "telemetry": collect_snapshot(),
        }

    if cmd == "protocol":
        key = arg.lower().replace(" ", "_").replace("-", "_")
        if not key or key not in PROTOCOLS:
            lines = ["AVAILABLE STARK PROTOCOLS", "------------------------------------------------------------------------"]
            for pk, pv in PROTOCOLS.items():
                lines.append(f"  {pk:<14} {pv['title']} — {pv['summary']}")
            return {"mode": "local", "kind": "protocol", "lines": lines}
        p = PROTOCOLS[key]
        settings = load_settings()
        settings["protocol"] = p["status"]
        settings["subsystems"] = dict(p["subsystems"])
        save_settings(settings)
        return {
            "mode": "local",
            "kind": "protocol",
            "lines": [
                f"EXECUTING {p['title']}",
                f"  Status : {p['status']}",
                f"  Action : {p['summary']}",
            ],
            "telemetry": collect_snapshot(),
        }

    if cmd == "time":
        t = collect_snapshot()
        return {
            "mode": "local",
            "kind": "info",
            "lines": [
                f"Local Time : {t['local_time']}",
                f"UTC Time   : {t['timestamp']}",
                f"Host Uptime: {t['system']['uptime_formatted']}",
            ],
        }

    if cmd in cmd_map:
        entry = cmd_map[cmd]
        try:
            outcome: ToolOutcome = entry["handler"](cmd, arg, {"dispatch": dispatch_command})
        except Exception as exc:
            return {
                "mode": "local",
                "kind": "error",
                "status": "failed",
                "summary": f"Module error in '{cmd}': {exc}",
                "lines": [f"Module '{entry.get('name', cmd)}' failed: {type(exc).__name__}: {exc}"],
                "telemetry": collect_snapshot(),
            }
        kind = "error" if outcome.status == "failed" else (
            "python" if cmd in ("py", "calc") else (
                "diag" if cmd in ("diag", "diagnostics") else (
                    "status" if cmd in ("status", "sysinfo", "telemetry") else "info"
                )
            )
        )
        res: dict[str, Any] = {
            "mode": "local",
            "kind": kind,
            "status": outcome.status,
            "summary": outcome.summary,
            "lines": outcome.lines or [outcome.summary],
            "telemetry": outcome.data.get("telemetry", collect_snapshot()),
        }
        if outcome.confirm_token:
            res["confirm_token"] = outcome.confirm_token
        return res

    # Route natural-language queries to AI
    query = arg if cmd == "ask" and arg else text
    return {
        "mode": "ai",
        "query": query,
        "system_prompt": render_system_prompt(len(actions), len(plugins)),
        "telemetry": collect_snapshot(),
    }


def query_ai_with_tools(
    prompt: str,
    system_prompt: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, list[str]]:
    _, _, combined = _active_tool_registry()
    return generate_chat_reply(
        prompt=prompt,
        system_prompt=system_prompt,
        history=history,
        dispatch_fn=dispatch_command,
        tool_registry=combined,
    )


def query_gemini_standalone(prompt: str, system_prompt: str, history: list[dict[str, str]] | None = None) -> str:
    reply, _traces = query_ai_with_tools(prompt, system_prompt, history=history)
    return reply


def interactive_repl() -> None:
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    notifications: list[str] = []
    scheduler = RoutineScheduler(dispatch_command, lambda msg: notifications.append(msg))
    scheduler.start()

    try:
        print()
        for line in ARC_REACTOR_ASCII:
            print(f"{CYAN}{line}{RESET}")
        t = collect_snapshot()
        snap = build_architecture_snapshot()
        print(f"\n{BOLD}{WHITE}  DEX // MARK LVII AURA TERMINAL{RESET}  {SLATE}·  Python {platform.python_version()}  ·  {t['suit']['designation']}{RESET}")
        print(f"{GREEN}  [ONLINE]{RESET} {WHITE}{len(snap['actions'])} actions · {len(snap['plugins'])} plugins · {len(snap['agents'])} agents loaded{RESET}")
        print(f"  {DIM}{SLATE}Type 'help' for commands, 'actions' to inspect modules, or ask DEX anything.{RESET}\n")

        chat_history: list[dict[str, str]] = []
        while True:
            while notifications:
                print(f"{PURPLE}[ROUTINE]{RESET} {WHITE}{notifications.pop(0)}{RESET}")
            try:
                raw = input(f"{BLUE}dex@mark57{RESET}{SLATE}:{RESET}{CYAN}~${RESET} ")
            except (EOFError, KeyboardInterrupt):
                print(f"\n{SLATE}Powering down DEX // Mark LVII terminal.{RESET}")
                break

            cleaned = raw.strip()
            if not cleaned:
                continue
            if cleaned.lower() in ("exit", "quit", "shutdown"):
                print(f"{SLATE}Shutting down DEX // Mark LVII terminal.{RESET}")
                break
            if cleaned.lower() == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                continue

            res = dispatch_command(cleaned)
            if res["mode"] == "local":
                color = RED if res.get("kind") == "error" else (CYAN if res.get("kind") in ("help", "status", "suit") else WHITE)
                for line in res.get("lines", []):
                    print(f"{color}{line}{RESET}")
                print()
            else:
                print(f"{DIM}{SLATE}Consulting DEX neural core...{RESET}")
                reply, traces = query_ai_with_tools(res["query"], res["system_prompt"], history=chat_history)
                for tr in traces:
                    print(f"{PURPLE}{tr}{RESET}")
                print(f"{CYAN}DEX >{RESET} {WHITE}{reply}{RESET}\n")
                chat_history.append({"role": "user", "text": res["query"]})
                chat_history.append({"role": "assistant", "text": reply})
    finally:
        scheduler.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="DEX // Mark LVII AURA Terminal")
    parser.add_argument("--exec", dest="exec_cmd", help="Execute a single command and exit")
    parser.add_argument("--json", action="store_true", help="Output structured JSON for --exec")
    parser.add_argument("--arch", action="store_true", help="Print full Mark LVII module snapshot as JSON")
    parser.add_argument("--cli", action="store_true", help="Run line-by-line REPL instead of full-screen TUI")
    parser.add_argument(
        "--preview",
        choices=["startup", "dashboard", "chat", "plugins", "actions", "memory", "settings", "voice", "armor"],
        help="Render a styled AURA Terminal screen once and exit",
    )
    args = parser.parse_args()

    if args.arch:
        print(json.dumps(build_architecture_snapshot()))
        return

    if args.preview:
        from tui import (
            get_term_width,
            render_armor_screen,
            render_chat_screen,
            render_dashboard,
            render_memory_screen,
            render_plugins_screen,
            render_settings_screen,
            render_startup_screen,
            render_voice_screen,
        )
        t = collect_snapshot()
        arch = build_architecture_snapshot()
        w = get_term_width()
        if args.preview == "startup":
            print(render_startup_screen(t, arch, w))
        elif args.preview == "dashboard":
            print(render_dashboard(t, arch, [], w))
        elif args.preview == "chat":
            print(render_chat_screen(t, [], w))
        elif args.preview in ("plugins", "actions"):
            tab = "actions" if args.preview == "actions" else "plugins"
            print(render_plugins_screen(t, arch, 0, w, module_tab=tab))
        elif args.preview == "memory":
            print(render_memory_screen(t, arch, 0, w))
        elif args.preview == "settings":
            print(render_settings_screen(t, arch, 0, 0, w))
        elif args.preview == "voice":
            print(render_voice_screen(t, arch, w))
        elif args.preview == "armor":
            print(render_armor_screen(t, dispatch_command("diag").get("lines", []), w))
        return

    if args.exec_cmd is not None:
        res = dispatch_command(args.exec_cmd)
        if args.json:
            print(json.dumps(res))
        else:
            for line in res.get("lines", []):
                print(line)
        return

    if args.cli:
        interactive_repl()
        return

    from tui import run_tui
    run_tui(dispatch_command, collect_snapshot, build_architecture_snapshot, query_ai_with_tools, render_system_prompt)


if __name__ == "__main__":
    main()
