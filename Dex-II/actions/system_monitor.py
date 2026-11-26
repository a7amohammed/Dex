"""Real-time CPU, RAM, Disk, Python, and Mark Suit telemetry monitor."""

from __future__ import annotations

import datetime
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from core.outcome import ToolOutcome
from memory.config_manager import MARK_SUITS, load_settings
from memory.memory_manager import load_memory

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = BASE_DIR.parent

TOOL = {
    "name": "system_monitor",
    "description": "Collect real-time CPU, memory, disk, uptime, Python, and Mark armor telemetry.",
    "commands": ["status", "sysinfo", "diag", "diagnostics", "telemetry"],
}


def read_memory_info() -> dict[str, Any]:
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            vals: dict[str, int] = {}
            for line in meminfo_path.read_text(encoding="utf-8").splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    num_str = parts[1].strip().split()[0]
                    if num_str.isdigit():
                        vals[key] = int(num_str)
            total_kb = vals.get("MemTotal", 0)
            avail_kb = vals.get("MemAvailable", vals.get("MemFree", 0))
            used_kb = max(0, total_kb - avail_kb)
            pct = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0.0
            return {
                "total_gb": round(total_kb / (1024 * 1024), 2),
                "used_gb": round(used_kb / (1024 * 1024), 2),
                "available_gb": round(avail_kb / (1024 * 1024), 2),
                "percent": pct,
            }
        except Exception:
            pass
    return {"total_gb": 0.0, "used_gb": 0.0, "available_gb": 0.0, "percent": 0.0}


def read_cpu_info() -> dict[str, Any]:
    cores = os.cpu_count() or 1
    model = platform.processor() or platform.machine() or "x86_64"
    cpuinfo_path = Path("/proc/cpuinfo")
    if cpuinfo_path.exists():
        try:
            for line in cpuinfo_path.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass
    load_1, load_5, load_15 = (0.0, 0.0, 0.0)
    try:
        load_1, load_5, load_15 = os.getloadavg()
    except (AttributeError, OSError):
        pass
    cpu_pct = round(min(100.0, (load_1 / max(1, cores)) * 100.0), 1)
    return {
        "cores": cores,
        "model": model,
        "load_1m": round(load_1, 2),
        "load_5m": round(load_5, 2),
        "load_15m": round(load_15, 2),
        "utilization_pct": cpu_pct,
    }


def read_uptime_seconds() -> float:
    uptime_path = Path("/proc/uptime")
    if uptime_path.exists():
        try:
            return float(uptime_path.read_text(encoding="utf-8").split()[0])
        except Exception:
            pass
    return 0.0


def format_duration(seconds: float) -> str:
    sec = int(max(0, seconds))
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02d}h {mins:02d}m"
    return f"{hours:02d}h {mins:02d}m {secs:02d}s"


def collect_snapshot() -> dict[str, Any]:
    settings = load_settings()
    suit = MARK_SUITS.get(settings["active_suit"], MARK_SUITS["mark57"])
    disk = shutil.disk_usage(WORKSPACE_ROOT)
    disk_pct = round((disk.used / disk.total) * 100, 1) if disk.total > 0 else 0.0
    mem = read_memory_info()
    cpu = read_cpu_info()
    uptime_s = read_uptime_seconds()
    memory_store = load_memory()

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "local_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "arch": platform.machine(),
            "hostname": platform.node(),
            "uptime_seconds": round(uptime_s, 1),
            "uptime_formatted": format_duration(uptime_s),
        },
        "cpu": cpu,
        "memory": mem,
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk_pct,
        },
        "suit": suit,
        "protocol": settings.get("protocol", "STANDBY"),
        "subsystems": settings.get("subsystems", {}),
        "facts_count": len(memory_store.get("facts", [])),
    }


def make_bar(pct: float, width: int = 20) -> str:
    clamped = max(0.0, min(100.0, pct))
    filled = int(round((clamped / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {clamped:5.1f}%"


def handler(cmd: str, _arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    t = collect_snapshot()
    if cmd == "telemetry":
        return ToolOutcome(status="done", summary="Telemetry collected.", lines=[], data={"telemetry": t})

    if cmd in ("diag", "diagnostics"):
        cpu_state = "NOMINAL" if t["cpu"]["utilization_pct"] < 80 else "ELEVATED"
        mem_state = "NOMINAL" if t["memory"]["percent"] < 85 else "ELEVATED"
        disk_state = "NOMINAL" if t["disk"]["percent"] < 90 else "WARNING"
        lines = [
            "RUNNING MARK LVII MULTI-STAGE DIAGNOSTIC SWEEP...",
            f"  [PASS] Python Interpreter       Python {t['python']['version']} verified",
            f"  [PASS] Arc Reactor Core         {t['suit']['core']} ({t['suit']['power_output_gw']} GW)",
            f"  [{'PASS' if cpu_state == 'NOMINAL' else 'WARN'}] Processor Headroom       {cpu_state} ({t['cpu']['cores']} cores @ {t['cpu']['utilization_pct']}% load)",
            f"  [{'PASS' if mem_state == 'NOMINAL' else 'WARN'}] Memory Allocation        {mem_state} ({t['memory']['available_gb']} GB available)",
            f"  [{'PASS' if disk_state == 'NOMINAL' else 'WARN'}] Solid-State Storage      {disk_state} ({t['disk']['free_gb']} GB free)",
            f"  [PASS] Armor Integrity          {t['suit']['designation']} hull at {t['suit']['armor_integrity']}%",
            "DIAGNOSTIC COMPLETE — All primary systems operating within Stark safety parameters, sir.",
        ]
        return ToolOutcome(status="done", summary="Diagnostic complete.", lines=lines, data={"telemetry": t})

    suit = t["suit"]
    sub = t["subsystems"]
    lines = [
        f"STARK INDUSTRIES TELEMETRY  ·  {t['local_time']}",
        "------------------------------------------------------------------------",
        f"  ACTIVE CHASSIS   {suit['designation']} ({suit['codename']})  ·  Integrity {suit['armor_integrity']}%",
        f"  PROTOCOL STATE   {t['protocol']}",
        f"  PYTHON RUNTIME   Python {t['python']['version']} ({t['python']['implementation']})",
        f"  HOST SYSTEM      {t['system']['os']} {t['system']['arch']}  ·  Uptime {t['system']['uptime_formatted']}",
        f"  CPU LOAD         {make_bar(t['cpu']['utilization_pct'])}  ({t['cpu']['cores']} cores, load {t['cpu']['load_1m']})",
        f"  MEMORY           {make_bar(t['memory']['percent'])}  ({t['memory']['used_gb']} / {t['memory']['total_gb']} GB)",
        f"  STORAGE          {make_bar(t['disk']['percent'])}  ({t['disk']['used_gb']} / {t['disk']['total_gb']} GB)",
        "",
        "SUBSYSTEM POWER ALLOCATION",
        f"  ARC REACTOR      {make_bar(sub.get('reactor', 96))}",
        f"  REPULSORS        {make_bar(sub.get('repulsors', 84))}",
        f"  FLIGHT THRUSTERS {make_bar(sub.get('thrusters', 78))}",
        f"  SHIELD MATRIX    {make_bar(sub.get('shielding', 90))}",
        f"  SENSOR ARRAY     {make_bar(sub.get('sensors', 95))}",
    ]
    return ToolOutcome(status="done", summary="Status telemetry generated.", lines=lines, data={"telemetry": t})
