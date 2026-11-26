"""AURA TERMINAL — Full-screen non-blocking ANSI Terminal User Interface for DEX (Mark LVII).

Pure Python 3.10+ standard library: TrueColor ANSI cyberpunk aura palette,
non-blocking POSIX select() render loop, interactive Settings [S] across 12 categories,
CTRL+SPACE (and fallback CTRL+G) live voice pipeline, Plugins & Actions manager,
and non-destructive Long-Term Memory / Task / Routine manager.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

from core.action_loader import toggle_action
from core.audio_devices import list_audio_devices
from core.gemini import GeminiLiveVoiceSession
from core.plugin_loader import approve_plugin, toggle_plugin
from core.routines.engine import RoutineScheduler, mark_routine_run
from core.tasks.engine import cancel_task, resume_task, start_task, steer_task
from memory.config_manager import (
    THEMES,
    export_config_backup,
    list_config_backups,
    load_api_keys,
    load_settings,
    mask_key,
    restore_config_backup,
    save_api_key,
    save_settings,
)
from memory.memory_manager import add_fact, load_memory, remove_fact, search_facts
from providers.audio import render_waveform_glyphs
from providers.base import LiveEvent

BG_RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

GREEN = "\033[38;2;16;185;129m"
AMBER = "\033[38;2;245;158;11m"
RED = "\033[38;2;239;68;68m"
WHITE = "\033[38;2;241;245;249m"
SLATE = "\033[38;2;148;163;184m"
DARK_BORDER = "\033[38;2;51;65;85m"

ANSI_RE = re.compile(r"\033\[[0-9;]*m")

DEX_LOGO = [
    "██████╗ ███████╗██╗  ██╗",
    "██╔══██╗██╔════╝╚██╗██╔╝",
    "██║  ██║█████╗   ╚███╔╝ ",
    "██║  ██║██╔══╝   ██╔██╗ ",
    "██████╔╝███████╗██╔╝ ██╗",
    "╚═════╝ ╚══════╝╚═╝  ╚═╝",
]

AURA_CORES = [
    [
        "     . - ~ ~ - .     ",
        "   .'  /  |  \\  '.   ",
        "  /   / _.-._ \\   \\  ",
        " |---+-(  ◎  )-+---| ",
        "  \\   \\ '-.-' /   /  ",
        "   '.  \\  |  /  .'   ",
        "     ' - ~ ~ - '     ",
    ],
    [
        "     . ~ - - ~ .     ",
        "   .'  \\  |  /  '.   ",
        "  /   / _.*._ \\   \\  ",
        " |---~-(  ◈  )-~---| ",
        "  \\   \\ '.*.' /   /  ",
        "   '.  /  |  \\  .'   ",
        "     ' ~ - - ~ '     ",
    ],
]

PULSE_GLYPHS = ["◇", "◈", "◆", "◈"]

SETTINGS_CATEGORIES = [
    ("themes", "1. Themes & Colors"),
    ("animations", "2. Animations"),
    ("layout", "3. Terminal Layout"),
    ("audio", "4. Audio Devices"),
    ("mic", "5. Mic Configuration"),
    ("voice", "6. Voice Preferences"),
    ("ai", "7. AI Providers & Keys"),
    ("plugins", "8. Plugins Control"),
    ("actions", "9. Actions Control"),
    ("shortcuts", "10. Keyboard Shortcuts"),
    ("performance", "11. Performance"),
    ("backup", "12. Config Backup & Restore"),
]


def _rgb(code: str) -> str:
    return f"\033[38;2;{code}m"


def get_palette(settings: dict[str, Any] | None = None) -> dict[str, str]:
    s = settings or load_settings()
    theme_key = s.get("theme", "cyberpunk_aura")
    t = THEMES.get(theme_key, THEMES["cyberpunk_aura"])
    return {
        "primary": _rgb(t["primary"]),
        "secondary": _rgb(t["secondary"]),
        "accent": _rgb(t["accent"]),
        "border": _rgb(t["border"]),
    }


def visible_len(text: str) -> int:
    return len(ANSI_RE.sub("", text))


def truncate_ansi(text: str, max_width: int) -> str:
    if visible_len(text) <= max_width:
        return text
    out: list[str] = []
    vis = 0
    i = 0
    limit = max(1, max_width - 1)
    while i < len(text) and vis < limit:
        if text[i] == "\033":
            m = ANSI_RE.match(text, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        out.append(text[i])
        vis += 1
        i += 1
    out.append(f"…{BG_RESET}")
    return "".join(out)


def pad_ansi(text: str, width: int) -> str:
    clipped = truncate_ansi(text, width)
    vis = visible_len(clipped)
    if vis >= width:
        return clipped
    return clipped + (" " * (width - vis))


def meter(pct: float, width: int = 16, color: str = "\033[38;2;0;240;255m") -> str:
    clamped = max(0.0, min(100.0, pct))
    filled = int(round((clamped / 100.0) * width))
    return f"{color}{'█' * filled}{DARK_BORDER}{'░' * (width - filled)}{BG_RESET} {WHITE}{clamped:5.1f}%{BG_RESET}"


def get_term_width() -> int:
    cols = shutil.get_terminal_size((96, 30)).columns
    return max(78, min(114, cols))


def box_line(inner: str, width: int, border_color: str) -> str:
    inner_w = width - 4
    return f"{border_color}║{BG_RESET} {pad_ansi(inner, inner_w)} {border_color}║{BG_RESET}"


def _active_wave_str(bars: list[int] | None, listening: bool, anim_enabled: bool, bar_count: int, pal: dict[str, str]) -> str:
    levels = list(bars or [])
    if len(levels) < bar_count:
        levels.extend([0] * (bar_count - len(levels)))
    levels = levels[:bar_count]
    if listening:
        return f"{pal['primary']}{render_waveform_glyphs(levels)}{BG_RESET}"
    if anim_enabled:
        return f"{DARK_BORDER}{'▁' * bar_count}{BG_RESET}"
    return f"{DARK_BORDER}{'-' * bar_count}{BG_RESET}"


def render_startup_screen(telemetry: dict[str, Any], arch: dict[str, Any], width: int | None = None, frame_idx: int = 0) -> str:
    w = width or get_term_width()
    inner_w = w - 2
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    plat = arch.get("platform", {})
    distro = plat.get("distro", {}).get("pretty_name", telemetry["system"]["os"])
    audio_backend = plat.get("audio", {}).get("backend", "Unknown")
    pulse = PULSE_GLYPHS[frame_idx % len(PULSE_GLYPHS)] if s["animations"]["enabled"] else "◈"

    lines: list[str] = [
        f"{c_brd}╔{'═' * inner_w}╗{BG_RESET}",
        box_line(
            f"{c_pri}{BOLD}{pulse} AURA TERMINAL{BG_RESET}   {SLATE}·   {s.get('assistant_name', 'DEX')} // MARK LVII   ·   {distro} ({plat.get('display_server', 'TTY')}){BG_RESET}",
            w,
            c_brd,
        ),
        box_line("", w, c_brd),
    ]

    pad_left = max(2, (inner_w - 28) // 2)
    for idx, row in enumerate(DEX_LOGO):
        color = c_pri if idx < 2 else (c_sec if idx < 4 else c_acc)
        lines.append(box_line(f"{' ' * pad_left}{color}{BOLD}{row}{BG_RESET}", w, c_brd))

    subtitle = "D E X   ·   N E U R A L   T E R M I N A L   C O R E"
    sub_pad = max(2, (inner_w - len(subtitle)) // 2)
    lines.extend([
        box_line("", w, c_brd),
        box_line(f"{' ' * sub_pad}{c_sec}{subtitle}{BG_RESET}", w, c_brd),
        box_line("", w, c_brd),
        box_line(f"{c_pri}  [●] Runtime & OS{BG_RESET} .......... {GREEN}ONLINE{BG_RESET} (Python {telemetry['python']['version']} · {telemetry['system']['arch']})", w, c_brd),
        box_line(f"{c_sec}  [●] Bundled Actions{BG_RESET} ....... {GREEN}{len(arch.get('actions', []))} ACTIVE{BG_RESET} / {len(arch.get('all_actions', []))} total", w, c_brd),
        box_line(f"{c_acc}  [●] Drop-In Plugins{BG_RESET} ....... {GREEN}{len(arch.get('plugins', []))} ACTIVE{BG_RESET} / {len(arch.get('all_plugins', []))} total", w, c_brd),
        box_line(f"{c_pri}  [●] Audio Stack{BG_RESET} ........... {WHITE}{audio_backend}{BG_RESET}", w, c_brd),
        box_line(f"{c_sec}  [●] Suit Profile{BG_RESET} .......... {WHITE}{telemetry['suit']['designation']} ({telemetry['suit']['codename']}){BG_RESET}", w, c_brd),
        box_line("", w, c_brd),
        box_line(
            f"{SLATE}  Press {WHITE}[ENTER]{SLATE} Aura Deck   {WHITE}[1-4]{SLATE} Direct Screen   {WHITE}[S]{SLATE} Settings   {WHITE}[Ctrl+Space]{SLATE} Voice   {WHITE}[Q]{SLATE} Quit{BG_RESET}",
            w,
            c_brd,
        ),
        f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}",
    ])
    return "\n".join(lines)


def render_header(active_tab: int, telemetry: dict[str, Any], width: int, frame_idx: int = 0, voice_state: str = "IDLE") -> list[str]:
    inner_w = width - 2
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    pulse = PULSE_GLYPHS[frame_idx % len(PULSE_GLYPHS)] if s["animations"]["enabled"] else "◈"

    tabs = [
        (1, "Aura Deck"),
        (2, "Neural Chat"),
        (3, "Plugins & Actions"),
        (4, "Memory & Tasks"),
    ]
    nav_parts = []
    for num, label in tabs:
        if num == active_tab:
            nav_parts.append(f"{c_pri}{BOLD}[{num}] {label}*{BG_RESET}")
        else:
            nav_parts.append(f"{SLATE}[{num}] {label}{BG_RESET}")
    if active_tab == 5:
        nav_parts.append(f"{c_acc}{BOLD}[S] Settings*{BG_RESET}")
    else:
        nav_parts.append(f"{SLATE}[S] Settings{BG_RESET}")

    nav = "  ".join(nav_parts)
    v_badge = f" {GREEN}[MIC:{voice_state}]{BG_RESET}" if voice_state == "LISTENING" else ""
    title = f"{c_pri}{BOLD}{pulse} {s.get('assistant_name', 'DEX')} // MARK LVII{BG_RESET}{v_badge}"
    gap = max(1, width - 4 - visible_len(title) - visible_len(nav))
    return [
        f"{c_brd}╔{'═' * inner_w}╗{BG_RESET}",
        box_line(f"{title}{' ' * gap}{nav}", width, c_brd),
        f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}",
    ]


def render_dashboard(
    telemetry: dict[str, Any],
    arch: dict[str, Any],
    history_log: list[str],
    width: int,
    frame_idx: int = 0,
    waveform_bars: list[int] | None = None,
    voice_state: str = "IDLE",
) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    inner_w = width - 2
    lines = render_header(1, telemetry, width, frame_idx=frame_idx, voice_state=voice_state)

    left_w = (inner_w - 1) // 2
    right_w = inner_w - 1 - left_w

    cpu = telemetry["cpu"]
    mem = telemetry["memory"]
    disk = telemetry["disk"]
    suit = telemetry["suit"]
    sub = telemetry["subsystems"]
    plat = arch.get("platform", {})
    audio_info = plat.get("audio", {})

    core_art = AURA_CORES[(frame_idx // 2) % len(AURA_CORES)] if s["animations"]["aura_pulse"] else AURA_CORES[0]
    wave = _active_wave_str(
        waveform_bars,
        voice_state == "LISTENING",
        bool(s["animations"]["enabled"]),
        int(s["animations"].get("waveform_bars", 24)),
        pal,
    )

    left_rows = [
        f"{c_pri}{BOLD}SYSTEM TELEMETRY{BG_RESET}",
        f"{DARK_BORDER}{'─' * (left_w - 2)}{BG_RESET}",
        f"{SLATE}CPU {BG_RESET} {meter(cpu['utilization_pct'], 14, c_pri)} {SLATE}({cpu['cores']}c){BG_RESET}",
        f"{SLATE}RAM {BG_RESET} {meter(mem['percent'], 14, c_sec)} {SLATE}{mem['used_gb']}/{mem['total_gb']}G{BG_RESET}",
        f"{SLATE}DISK{BG_RESET} {meter(disk['percent'], 14, c_acc)} {SLATE}{disk['free_gb']}G free{BG_RESET}",
        f"{SLATE}HOST{BG_RESET} {WHITE}{plat.get('distro', {}).get('supported_name', telemetry['system']['os'])}{BG_RESET} · {SLATE}{plat.get('display_server', 'TTY')}{BG_RESET}",
        "",
        f"{c_pri}{BOLD}SUBSYSTEM POWER{BG_RESET}",
        f"{SLATE}Reactor  {BG_RESET}{meter(sub.get('reactor', 96), 12, c_pri)}",
        f"{SLATE}Repulsor {BG_RESET}{meter(sub.get('repulsors', 84), 12, c_sec)}",
        f"{SLATE}Shield   {BG_RESET}{meter(sub.get('shielding', 90), 12, c_acc)}",
    ]

    right_rows = [
        f"{c_acc}{BOLD}DEX AURA CORE // {suit['designation'].upper()}{BG_RESET}",
        f"{DARK_BORDER}{'─' * (right_w - 2)}{BG_RESET}",
        *[f"     {c_pri if i in (2, 3, 4) else c_sec}{r}{BG_RESET}" for i, r in enumerate(core_art)],
        f"{SLATE}AI Engine:{BG_RESET} {WHITE}{s['ai']['provider'].upper()} ({s['ai']['gemini_model']}){BG_RESET}",
        f"{SLATE}Voice    :{BG_RESET} {GREEN if audio_info.get('voice_capture_ready') else AMBER}{voice_state}{BG_RESET} · {SLATE}{audio_info.get('backend', 'Headless')}{BG_RESET}",
        f"{SLATE}Modules  :{BG_RESET} {WHITE}{len(arch.get('actions', []))} actions · {len(arch.get('plugins', []))} plugins · {arch.get('memory_summary', {}).get('facts_count', 0)} memories{BG_RESET}",
    ]

    max_rows = max(len(left_rows), len(right_rows))
    for i in range(max_rows):
        ltxt = left_rows[i] if i < len(left_rows) else ""
        rtxt = right_rows[i] if i < len(right_rows) else ""
        lines.append(
            f"{c_brd}║{BG_RESET} {pad_ansi(ltxt, left_w - 2)} {c_brd}│{BG_RESET} {pad_ansi(rtxt, right_w - 2)} {c_brd}║{BG_RESET}"
        )

    if s["layout"].get("show_waveform", True):
        lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
        lines.append(
            box_line(
                f"{c_pri}AUDIO WAVEFORM [{voice_state:<10}]{BG_RESET}  {wave}  {SLATE}(Ctrl+Space / Ctrl+G){BG_RESET}",
                width,
                c_brd,
            )
        )

    if s["layout"].get("show_feed", True):
        lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
        lines.append(box_line(f"{c_pri}{BOLD}RECENT EVENT FEED{BG_RESET}", width, c_brd))
        feed_count = 3 if s["layout"].get("density") == "compact" else 4
        items = history_log[-feed_count:] or [f"{SLATE}Awaiting directive. Press [2] to chat or [/] to execute a command.{BG_RESET}"]
        for item in items:
            lines.append(box_line(f"  {item}", width, c_brd))

    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(
        box_line(
            f"{SLATE}[1-4] Switch   [S] Settings   [Ctrl+Space / Ctrl+G] Voice   [/] Command   [D] Diag   [Q] Quit{BG_RESET}",
            width,
            c_brd,
        )
    )
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def render_chat_screen(
    telemetry: dict[str, Any],
    transcript: list[str],
    width: int,
    frame_idx: int = 0,
    voice_state: str = "IDLE",
) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_brd = pal["primary"], pal["secondary"], pal["border"]
    inner_w = width - 2
    lines = render_header(2, telemetry, width, frame_idx=frame_idx, voice_state=voice_state)
    lines.append(
        box_line(
            f"{SLATE}CHANNEL: {c_pri}#dex-neural{BG_RESET}   {SLATE}·   ENGINE: {WHITE}{s['ai']['provider'].upper()}{BG_RESET}   {SLATE}·   SUIT: {WHITE}{telemetry['suit']['designation']}{BG_RESET}",
            width,
            c_brd,
        )
    )
    lines.append(box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd))

    visible_msgs = transcript[-14:] if transcript else [
        f"{c_pri}DEX >{BG_RESET} {WHITE}AURA Terminal online. All local actions, plugins, routines, and memory systems are ready.{BG_RESET}",
        f"{SLATE}Press [Enter] or [/] to type a command (`diag`, `suit mark50`, `task list`, `py 2**16`) or ask DEX anything.{BG_RESET}",
    ]
    for msg in visible_msgs:
        lines.append(box_line(msg, width, c_brd))
    for _ in range(max(0, 14 - len(visible_msgs))):
        lines.append(box_line("", width, c_brd))

    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(box_line(f"{c_sec}dex@mark57:~$ {SLATE}(Press [Enter] or [/] to compose · [Ctrl+Space] Voice input){BG_RESET}", width, c_brd))
    lines.append(box_line(f"{SLATE}[Enter / /] Input   [C] Clear   [S] Settings   [1-4] Switch   [Q] Quit{BG_RESET}", width, c_brd))
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def _status_badge(status: str, pal: dict[str, str]) -> str:
    st = status.lower()
    if st == "active":
        return f"{GREEN}ACTIVE    {BG_RESET}"
    if st == "disabled":
        return f"{SLATE}DISABLED  {BG_RESET}"
    if st == "quarantined":
        return f"{AMBER}QUARANTINE{BG_RESET}"
    if st == "missing_dep":
        return f"{AMBER}MISSINGDEP{BG_RESET}"
    return f"{RED}ERROR     {BG_RESET}"


def render_plugins_screen(
    telemetry: dict[str, Any],
    arch: dict[str, Any],
    selected_idx: int,
    width: int,
    module_tab: str = "plugins",
    show_detail: bool = False,
    frame_idx: int = 0,
    voice_state: str = "IDLE",
) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    inner_w = width - 2
    lines = render_header(3, telemetry, width, frame_idx=frame_idx, voice_state=voice_state)

    plugins_list = arch.get("all_plugins", arch.get("plugins", []))
    actions_list = arch.get("all_actions", arch.get("actions", []))
    active_list = plugins_list if module_tab == "plugins" else actions_list

    tab_p = f"{c_pri}{BOLD}[ PLUGINS ({len(plugins_list)}) ]{BG_RESET}" if module_tab == "plugins" else f"{SLATE}  PLUGINS ({len(plugins_list)})  {BG_RESET}"
    tab_a = f"{c_sec}{BOLD}[ ACTIONS ({len(actions_list)}) ]{BG_RESET}" if module_tab == "actions" else f"{SLATE}  ACTIONS ({len(actions_list)})  {BG_RESET}"
    lines.append(box_line(f"{tab_p}   {tab_a}   {SLATE}([Tab] Switch · [Space] Enable/Disable · [R] Reload){BG_RESET}", width, c_brd))
    lines.append(box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd))

    list_rows = 10
    if active_list:
        idx_clamped = selected_idx % len(active_list)
        start = max(0, idx_clamped - list_rows + 1) if idx_clamped >= list_rows else 0
        window = active_list[start : start + list_rows]
        for offset, mod in enumerate(window):
            real_idx = start + offset
            is_sel = real_idx == idx_clamped
            pointer = f"{c_pri}▸{BG_RESET}" if is_sel else " "
            badge = _status_badge(mod.get("status", "active"), pal)
            cmds = ", ".join(mod.get("commands", [])[:3]) or "-"
            name_col = f"{WHITE}{BOLD}{mod['name']:<19}{BG_RESET}" if is_sel else f"{WHITE}{mod['name']:<19}{BG_RESET}"
            lines.append(box_line(f" {pointer} {badge} {name_col} {c_sec}[{cmds}]{BG_RESET}", width, c_brd))
        for _ in range(max(0, list_rows - len(window))):
            lines.append(box_line("", width, c_brd))

        sel = active_list[idx_clamped]
        lines.append(box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd))
        lines.append(box_line(f"{c_acc}SELECTED:{BG_RESET} {WHITE}{sel['file']}{BG_RESET} — {SLATE}{sel.get('description') or 'No description'}{BG_RESET}", width, c_brd))
        if sel.get("error"):
            lines.append(box_line(f"{AMBER}NOTICE  :{BG_RESET} {WHITE}{sel['error']}{BG_RESET}", width, c_brd))
        elif show_detail:
            deps = ", ".join(sel.get("dependencies", [])) or "stdlib only"
            risky = ", ".join(sel.get("risky_patterns", [])) or "none"
            lines.append(box_line(f"{c_sec}DETAILS :{BG_RESET} Deps=[{deps}] · Sensitive=[{risky}] · Trusted={sel.get('trusted', True)}", width, c_brd))
    else:
        lines.append(box_line(f"{SLATE}No modules discovered in this category.{BG_RESET}", width, c_brd))
        for _ in range(list_rows + 1):
            lines.append(box_line("", width, c_brd))

    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(
        box_line(
            f"{SLATE}[↑/↓] Select   [Tab] Plugins/Actions   [Space] Toggle   [A] Approve   [I] Info   [R] Reload   [T] Test{BG_RESET}",
            width,
            c_brd,
        )
    )
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def render_memory_screen(
    telemetry: dict[str, Any],
    arch: dict[str, Any],
    selected_idx: int,
    width: int,
    sub_tab: str = "memory",
    search_query: str = "",
    diag_lines: list[str] | None = None,
    frame_idx: int = 0,
    voice_state: str = "IDLE",
) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    inner_w = width - 2
    lines = render_header(4, telemetry, width, frame_idx=frame_idx, voice_state=voice_state)

    facts = search_facts(search_query) if search_query else load_memory().get("facts", [])
    tasks = arch.get("tasks", [])
    routines = arch.get("routines", [])

    t_mem = f"{c_pri}{BOLD}[ MEMORY ({len(facts)}) ]{BG_RESET}" if sub_tab == "memory" else f"{SLATE}  MEMORY ({len(facts)})  {BG_RESET}"
    t_tsk = f"{c_sec}{BOLD}[ TASKS ({len(tasks)}) ]{BG_RESET}" if sub_tab == "tasks" else f"{SLATE}  TASKS ({len(tasks)})  {BG_RESET}"
    t_rtn = f"{c_acc}{BOLD}[ ROUTINES & DIAG ]{BG_RESET}" if sub_tab == "routines" else f"{SLATE}  ROUTINES & DIAG  {BG_RESET}"
    lines.append(box_line(f"{t_mem}  {t_tsk}  {t_rtn}   {SLATE}([Tab] Switch View){BG_RESET}", width, c_brd))
    lines.append(box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd))

    body_rows = 11
    if sub_tab == "memory":
        if search_query:
            lines.append(box_line(f"{c_acc}FILTER:{BG_RESET} '{WHITE}{search_query}{BG_RESET}' ({len(facts)} matches) — press [C] to clear", width, c_brd))
            body_rows -= 1
        if facts:
            idx_c = selected_idx % len(facts)
            start = max(0, idx_c - body_rows + 1) if idx_c >= body_rows else 0
            window = facts[start : start + body_rows]
            for off, f_item in enumerate(window):
                ptr = f"{c_pri}▸{BG_RESET}" if (start + off) == idx_c else " "
                fid = f_item.get("id", "mem")
                cat = f_item.get("category", "general")
                txt = f_item.get("text", "")
                lines.append(box_line(f" {ptr} {c_sec}{fid}{BG_RESET} {SLATE}[{cat}]{BG_RESET} {WHITE}{txt}{BG_RESET}", width, c_brd))
            for _ in range(max(0, body_rows - len(window))):
                lines.append(box_line("", width, c_brd))
        else:
            lines.append(box_line(f"{SLATE}No long-term memory entries match. Press [N] to store a new fact.{BG_RESET}", width, c_brd))
            for _ in range(body_rows - 1):
                lines.append(box_line("", width, c_brd))
        footer = "[↑/↓] Select   [N] Add Fact   [F] Search   [X] Delete Fact   [C] Clear Filter   [Tab] Tasks"

    elif sub_tab == "tasks":
        if tasks:
            idx_c = selected_idx % len(tasks)
            window = tasks[:body_rows]
            for off, t_item in enumerate(window):
                ptr = f"{c_pri}▸{BG_RESET}" if off == idx_c else " "
                st = t_item.get("status", "unknown").upper()
                st_c = GREEN if st == "COMPLETED" else (AMBER if st == "CANCELLED" else c_sec)
                lines.append(
                    box_line(
                        f" {ptr} {c_sec}{t_item.get('id', '?')}{BG_RESET} [{st_c}{st:<9}{BG_RESET}] {WHITE}{t_item.get('goal', '')}{BG_RESET}",
                        width,
                        c_brd,
                    )
                )
            for _ in range(max(0, body_rows - len(window))):
                lines.append(box_line("", width, c_brd))
        else:
            lines.append(box_line(f"{SLATE}No background tasks recorded. Press [N] to launch an agent task.{BG_RESET}", width, c_brd))
            for _ in range(body_rows - 1):
                lines.append(box_line("", width, c_brd))
        footer = "[↑/↓] Select   [N] Start Task   [W] Steer   [U] Resume   [X] Cancel   [Tab] Routines & Diag"

    else:
        shown = 0
        for off, r in enumerate(routines[:4]):
            ptr = f"{c_pri}▸{BG_RESET}" if off == (selected_idx % max(1, len(routines[:4]))) else " "
            lines.append(
                box_line(
                    f" {ptr} {c_acc}{r['name']:<16}{BG_RESET} @{WHITE}{r['schedule']:<6}{BG_RESET} cmd={c_sec}{r['command']}{BG_RESET} last={SLATE}{r.get('last_run') or 'never'}{BG_RESET}",
                    width,
                    c_brd,
                )
            )
            shown += 1
        lines.append(box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd))
        shown += 1
        for dl in (diag_lines or [])[: max(1, body_rows - shown)]:
            color = GREEN if "[PASS]" in dl else (AMBER if "[WARN]" in dl else WHITE)
            lines.append(box_line(f"{color}{dl}{BG_RESET}", width, c_brd))
            shown += 1
        for _ in range(max(0, body_rows - shown)):
            lines.append(box_line("", width, c_brd))
        footer = "[R] Run Selected Routine   [D] Run Diag   [H] House Party Protocol   [U] Undo   [Tab] Memory"

    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(box_line(f"{SLATE}{footer}{BG_RESET}", width, c_brd))
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def _settings_items_for_category(cat_id: str, arch: dict[str, Any]) -> list[dict[str, str]]:
    s = load_settings()
    keys = load_api_keys()
    if cat_id == "themes":
        return [
            {"key": "theme", "label": "Active Theme", "val": THEMES[s["theme"]]["label"], "hint": "Enter/Space cycles theme"},
            {"key": "assistant_name", "label": "Assistant Identity", "val": s.get("assistant_name", "DEX"), "hint": "Enter edits name"},
        ]
    if cat_id == "animations":
        return [
            {"key": "anim_enabled", "label": "Terminal Animations", "val": str(s["animations"]["enabled"]), "hint": "Enter toggles"},
            {"key": "aura_pulse", "label": "Aura Core Pulse", "val": str(s["animations"]["aura_pulse"]), "hint": "Enter toggles"},
            {"key": "waveform_bars", "label": "Waveform Bar Count", "val": str(s["animations"]["waveform_bars"]), "hint": "Enter cycles 16/24/32"},
        ]
    if cat_id == "layout":
        return [
            {"key": "density", "label": "Layout Density", "val": s["layout"]["density"], "hint": "Enter cycles balanced/compact/expanded"},
            {"key": "show_waveform", "label": "Show Audio Waveform", "val": str(s["layout"]["show_waveform"]), "hint": "Enter toggles"},
            {"key": "show_feed", "label": "Show Recent Event Feed", "val": str(s["layout"]["show_feed"]), "hint": "Enter toggles"},
        ]
    if cat_id == "audio":
        devs = list_audio_devices()
        return [
            {"key": "input_device", "label": "Audio Input Device", "val": f"{s['audio']['input_device']} ({len(devs['inputs'])} found)", "hint": "Enter cycles probed inputs"},
            {"key": "output_device", "label": "Audio Output Device", "val": f"{s['audio']['output_device']} ({len(devs['outputs'])} found)", "hint": "Enter cycles probed outputs"},
            {"key": "audio_backend", "label": "Detected Capture Tool", "val": str(devs.get("capture_tool") or "None (headless)"), "hint": "Read-only system probe"},
        ]
    if cat_id == "mic":
        return [
            {"key": "mic_gain", "label": "Microphone Gain", "val": f"{s['audio']['mic_gain']:.1f}x", "hint": "Enter increases (+0.2x, wraps 0.6..2.0)"},
            {"key": "sample_rate_in", "label": "Capture Sample Rate", "val": f"{s['audio']['sample_rate_in']} Hz", "hint": "PCM16 mono input"},
        ]
    if cat_id == "voice":
        ww = s.get("wakeword", {})
        return [
            {"key": "stt_provider", "label": "STT Provider", "val": s["voice"]["stt_provider"], "hint": "Enter cycles auto/gemini_live/whisper/none"},
            {"key": "tts_provider", "label": "TTS Provider", "val": s["voice"]["tts_provider"], "hint": "Enter cycles system/piper/elevenlabs/none"},
            {"key": "voice_name", "label": "Voice Profile", "val": s["voice"]["voice_name"], "hint": "Enter edits voice tag (e.g. en-gb)"},
            {"key": "auto_speak", "label": "Auto-Speak Chat Replies", "val": str(s["voice"]["auto_speak"]), "hint": "Enter toggles"},
            {"key": "wakeword_enabled", "label": "Wake Word ('hey dex')", "val": "ENABLED" if ww.get("enabled") else "DISABLED", "hint": "Enter toggles openWakeWord passive trigger"},
            {"key": "wakeword_threshold", "label": "Wake Sensitivity", "val": f"{float(ww.get('threshold', 0.5)):.2f}", "hint": "Enter cycles 0.35 / 0.50 / 0.65 / 0.80"},
            {"key": "wakeword_model_path", "label": "Wake Model Path", "val": str(ww.get("model_path", "providers/wakewords/hey_dex.onnx")), "hint": "Enter edits ONNX/TFLite model path"},
        ]
    if cat_id == "ai":
        return [
            {"key": "ai_provider", "label": "Active AI Provider", "val": s["ai"]["provider"], "hint": "Enter toggles gemini / openai"},
            {"key": "gemini_model", "label": "Gemini Text Model", "val": s["ai"]["gemini_model"], "hint": "Enter cycles Gemini models"},
            {"key": "openai_model", "label": "OpenAI-Compatible Model", "val": s["ai"]["openai_model"], "hint": "Enter edits model name"},
            {"key": "GEMINI_API_KEY", "label": "Gemini API Key", "val": mask_key(keys.get("GEMINI_API_KEY", "")), "hint": "Enter prompts to set/clear key"},
            {"key": "OPENAI_API_KEY", "label": "OpenAI API Key", "val": mask_key(keys.get("OPENAI_API_KEY", "")), "hint": "Enter prompts to set/clear key"},
        ]
    if cat_id == "plugins":
        all_p = arch.get("all_plugins", [])
        return [
            {"key": f"plug:{p['filename']}", "label": f"Plugin: {p['name']}", "val": p["status"].upper(), "hint": "Enter toggles enable/disable"}
            for p in all_p[:8]
        ] or [{"key": "none", "label": "No plugins found", "val": "-", "hint": ""}]
    if cat_id == "actions":
        all_a = arch.get("all_actions", [])
        return [
            {"key": f"act:{a['filename']}", "label": f"Action: {a['name']}", "val": a["status"].upper(), "hint": "Enter toggles enable/disable"}
            for a in all_a[:8]
        ] or [{"key": "none", "label": "No actions found", "val": "-", "hint": ""}]
    if cat_id == "shortcuts":
        return [
            {"key": "sc_settings", "label": "Settings Shortcut", "val": s["shortcuts"]["settings"], "hint": "Default: s"},
            {"key": "sc_voice_pri", "label": "Voice Primary Shortcut", "val": s["shortcuts"]["voice_primary"], "hint": "Ctrl+Space (POSIX \\x00)"},
            {"key": "sc_voice_fb", "label": "Voice Fallback Shortcut", "val": s["shortcuts"]["voice_fallback"], "hint": "Ctrl+G (POSIX \\x07) if DE captures Ctrl+Space"},
        ]
    if cat_id == "performance":
        return [
            {"key": "tick_ms", "label": "Render Loop Tick (ms)", "val": f"{s['performance']['tick_ms']} ms", "hint": "Enter cycles 120/180/300 ms"},
            {"key": "bg_sched", "label": "Background Routine Scheduler", "val": str(s["performance"]["background_scheduler"]), "hint": "Enter toggles"},
        ]
    # backup
    backups = list_config_backups()
    items = [{"key": "create_backup", "label": "Create New Config Backup", "val": f"{len(backups)} saved", "hint": "Enter exports JSON backup"}]
    for b in backups[:5]:
        items.append({"key": f"restore:{b.name}", "label": f"Restore {b.name}", "val": "RESTORE", "hint": "Enter restores this snapshot"})
    return items


def render_settings_screen(
    telemetry: dict[str, Any],
    arch: dict[str, Any],
    cat_idx: int,
    opt_idx: int,
    width: int,
    status_note: str = "",
    frame_idx: int = 0,
    voice_state: str = "IDLE",
) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    inner_w = width - 2
    lines = render_header(5, telemetry, width, frame_idx=frame_idx, voice_state=voice_state)

    cat_idx_c = cat_idx % len(SETTINGS_CATEGORIES)
    cat_id, cat_title = SETTINGS_CATEGORIES[cat_idx_c]
    items = _settings_items_for_category(cat_id, arch)
    opt_idx_c = opt_idx % len(items) if items else 0

    left_w = 32
    right_w = inner_w - 1 - left_w

    left_rows = [f"{c_pri}{BOLD}CATEGORIES (12){BG_RESET}"]
    for idx, (_cid, label) in enumerate(SETTINGS_CATEGORIES):
        ptr = f"{c_pri}▸{BG_RESET}" if idx == cat_idx_c else " "
        txt_col = f"{WHITE}{BOLD}" if idx == cat_idx_c else SLATE
        left_rows.append(f" {ptr} {txt_col}{label}{BG_RESET}")

    right_rows = [
        f"{c_acc}{BOLD}{cat_title.upper()}{BG_RESET}",
        f"{DARK_BORDER}{'─' * (right_w - 2)}{BG_RESET}",
    ]
    for idx, item in enumerate(items[:9]):
        ptr = f"{c_pri}▸{BG_RESET}" if idx == opt_idx_c else " "
        right_rows.append(f" {ptr} {WHITE}{item['label']:<25}{BG_RESET} {c_sec}{item['val']}{BG_RESET}")
    if items:
        right_rows.append(f"{DARK_BORDER}{'─' * (right_w - 2)}{BG_RESET}")
        right_rows.append(f"{SLATE}Action: {WHITE}{items[opt_idx_c]['hint']}{BG_RESET}")
    if status_note:
        right_rows.append(f"{GREEN}{status_note}{BG_RESET}")

    max_rows = max(len(left_rows), len(right_rows))
    for i in range(max_rows):
        ltxt = left_rows[i] if i < len(left_rows) else ""
        rtxt = right_rows[i] if i < len(right_rows) else ""
        lines.append(
            f"{c_brd}║{BG_RESET} {pad_ansi(ltxt, left_w - 2)} {c_brd}│{BG_RESET} {pad_ansi(rtxt, right_w - 2)} {c_brd}║{BG_RESET}"
        )

    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(
        box_line(
            f"{SLATE}[←/→] Category   [↑/↓] Option   [Enter/Space] Modify   [Esc/S] Close Settings   [Q] Quit{BG_RESET}",
            width,
            c_brd,
        )
    )
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def render_voice_screen(
    telemetry: dict[str, Any],
    arch: dict[str, Any],
    width: int,
    voice_state: str = "IDLE",
    waveform_bars: list[int] | None = None,
    transcript: str = "",
    response: str = "",
    voice_events: list[str] | None = None,
    frame_idx: int = 0,
) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_sec, c_acc, c_brd = pal["primary"], pal["secondary"], pal["accent"], pal["border"]
    inner_w = width - 2
    lines = render_header(1, telemetry, width, frame_idx=frame_idx, voice_state=voice_state)

    audio = arch.get("platform", {}).get("audio", {})
    devs = arch.get("audio_devices", {})
    ww_cfg = s.get("wakeword", {})
    ww_info = arch.get("wakeword", {})
    wave = _active_wave_str(
        waveform_bars,
        voice_state == "LISTENING",
        bool(s["animations"]["enabled"]),
        int(s["animations"].get("waveform_bars", 24)),
        pal,
    )
    st_color = GREEN if voice_state == "LISTENING" else (AMBER if "UNAVAILABLE" in voice_state or "MISSING" in voice_state or "ERROR" in voice_state else c_pri)
    ww_label = f"{'ON' if ww_cfg.get('enabled') else 'OFF'} · '{ww_cfg.get('phrase', 'hey dex')}' (ready={ww_info.get('ready', False)})"

    lines.extend([
        box_line(f"{c_acc}{BOLD}DEX VOICE UPLINK // LIVE AUDIO INTERFACE{BG_RESET}   {SLATE}·   Shortcut: {WHITE}Ctrl+Space{SLATE} / {WHITE}Ctrl+G{BG_RESET}", width, c_brd),
        box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd),
        box_line(f"  {SLATE}Status       :{BG_RESET} {st_color}{BOLD}{voice_state}{BG_RESET}", width, c_brd),
        box_line(f"  {SLATE}Wake Word    :{BG_RESET} {WHITE}{ww_label}{BG_RESET}", width, c_brd),
        box_line(f"  {SLATE}Audio Stack  :{BG_RESET} {WHITE}{audio.get('backend', 'Unknown')}{BG_RESET}  (capture={devs.get('capture_tool') or 'none'}, playback={devs.get('playback_tool') or 'none'})", width, c_brd),
        box_line(f"  {SLATE}Input Device :{BG_RESET} {WHITE}{s['audio']['input_device']}{BG_RESET}   {SLATE}Gain:{BG_RESET} {WHITE}{s['audio']['mic_gain']:.1f}x{BG_RESET}   {SLATE}TTS:{BG_RESET} {WHITE}{s['voice']['tts_provider']}{BG_RESET}", width, c_brd),
        box_line("", width, c_brd),
        box_line(f"  {c_pri}LIVE WAVEFORM:{BG_RESET}  {wave}", width, c_brd),
        box_line("", width, c_brd),
        box_line(f"  {c_sec}Transcript   :{BG_RESET} {WHITE}{transcript or '(Waiting for spoken audio input)'}{BG_RESET}", width, c_brd),
        box_line(f"  {c_acc}DEX Response :{BG_RESET} {WHITE}{response or '(Idle)'}{BG_RESET}", width, c_brd),
        box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd),
    ])

    ev_list = (voice_events or [])[-4:] or [
        f"{SLATE}Press [Ctrl+Space] or [Ctrl+G] to toggle mic, or [W] to toggle openWakeWord ('hey dex').{BG_RESET}"
    ]
    for ev in ev_list:
        lines.append(box_line(f"  {ev}", width, c_brd))

    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(box_line(f"{SLATE}[Ctrl+Space / Ctrl+G] Toggle Mic   [W] Toggle 'hey dex'   [Esc] Close   [S] Settings{BG_RESET}", width, c_brd))
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def render_armor_screen(telemetry: dict[str, Any], diag_lines: list[str], width: int) -> str:
    s = load_settings()
    pal = get_palette(s)
    c_pri, c_brd = pal["primary"], pal["border"]
    inner_w = width - 2
    lines = render_header(4, telemetry, width)
    suit = telemetry["suit"]
    lines.append(box_line(f"{c_pri}{BOLD}ACTIVE CHASSIS:{BG_RESET} {WHITE}{suit['designation']} ({suit['codename']}){BG_RESET}   {SLATE}·   Max Speed: Mach {suit['max_mach']}   ·   {suit['power_output_gw']} GW{BG_RESET}", width, c_brd))
    lines.append(box_line(f"{DARK_BORDER}{'─' * (width - 4)}{BG_RESET}", width, c_brd))
    for dl in diag_lines[:12]:
        color = GREEN if "[PASS]" in dl else (AMBER if "[WARN]" in dl else WHITE)
        lines.append(box_line(f"{color}{dl}{BG_RESET}", width, c_brd))
    for _ in range(max(0, 12 - len(diag_lines[:12]))):
        lines.append(box_line("", width, c_brd))
    lines.append(f"{c_brd}╠{'═' * inner_w}╣{BG_RESET}")
    lines.append(box_line(f"{SLATE}[D] Re-run Diag   [H] House Party Protocol   [U] Undo Last   [1-4] Switch Screen   [Q] Quit{BG_RESET}", width, c_brd))
    lines.append(f"{c_brd}╚{'═' * inner_w}╝{BG_RESET}")
    return "\n".join(lines)


def _read_key_nonblocking(timeout_s: float) -> str | None:
    if os.name == "nt":
        import msvcrt
        if not msvcrt.kbhit():
            time.sleep(timeout_s)
            return None
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return ch + msvcrt.getwch()
        return ch

    import select
    r, _, _ = select.select([sys.stdin], [], [], timeout_s)
    if not r:
        return None
    ch = os.read(sys.stdin.fileno(), 1).decode("utf-8", errors="replace")
    if ch == "\033":
        r2, _, _ = select.select([sys.stdin], [], [], 0.03)
        if r2:
            seq = os.read(sys.stdin.fileno(), 2).decode("utf-8", errors="replace")
            return ch + seq
    return ch


def _prompt_line_posix(prompt_text: str, old_termios: Any) -> str:
    import termios
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSADRAIN, old_termios)
    sys.stdout.write("\033[?25h\n")
    sys.stdout.flush()
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    finally:
        import tty
        tty.setraw(fd)
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()


def _prompt_line(prompt_text: str, old_termios: Any = None) -> str:
    if os.name != "nt" and old_termios is not None:
        return _prompt_line_posix(prompt_text, old_termios)
    sys.stdout.write("\033[?25h\n")
    sys.stdout.flush()
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    finally:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()


def _apply_setting_action(key: str, prompt_fn: Callable[[str], str]) -> str:
    s = load_settings()
    if key == "theme":
        order = list(THEMES.keys())
        nxt = order[(order.index(s["theme"]) + 1) % len(order)]
        s["theme"] = nxt
        save_settings(s)
        return f"Theme switched to {THEMES[nxt]['label']}."
    if key == "assistant_name":
        val = prompt_fn("Assistant name (default DEX): ")
        if val:
            s["assistant_name"] = val[:24]
            save_settings(s)
            return f"Assistant renamed to {s['assistant_name']}."
        return "Unchanged."
    if key == "anim_enabled":
        s["animations"]["enabled"] = not s["animations"]["enabled"]
        save_settings(s)
        return f"Animations = {s['animations']['enabled']}."
    if key == "aura_pulse":
        s["animations"]["aura_pulse"] = not s["animations"]["aura_pulse"]
        save_settings(s)
        return f"Aura pulse = {s['animations']['aura_pulse']}."
    if key == "waveform_bars":
        opts = [16, 24, 32]
        cur = int(s["animations"].get("waveform_bars", 24))
        s["animations"]["waveform_bars"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 24
        save_settings(s)
        return f"Waveform bars = {s['animations']['waveform_bars']}."
    if key == "density":
        opts = ["balanced", "compact", "expanded"]
        cur = s["layout"].get("density", "balanced")
        s["layout"]["density"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else "balanced"
        save_settings(s)
        return f"Layout density = {s['layout']['density']}."
    if key == "show_waveform":
        s["layout"]["show_waveform"] = not s["layout"]["show_waveform"]
        save_settings(s)
        return f"Show waveform = {s['layout']['show_waveform']}."
    if key == "show_feed":
        s["layout"]["show_feed"] = not s["layout"]["show_feed"]
        save_settings(s)
        return f"Show event feed = {s['layout']['show_feed']}."
    if key == "input_device":
        devs = ["auto", *[d["id"] for d in list_audio_devices().get("inputs", [])]]
        cur = s["audio"]["input_device"]
        s["audio"]["input_device"] = devs[(devs.index(cur) + 1) % len(devs)] if cur in devs else "auto"
        save_settings(s)
        return f"Input device = {s['audio']['input_device']}."
    if key == "output_device":
        devs = ["auto", *[d["id"] for d in list_audio_devices().get("outputs", [])]]
        cur = s["audio"]["output_device"]
        s["audio"]["output_device"] = devs[(devs.index(cur) + 1) % len(devs)] if cur in devs else "auto"
        save_settings(s)
        return f"Output device = {s['audio']['output_device']}."
    if key == "mic_gain":
        cur = float(s["audio"].get("mic_gain", 1.0))
        nxt = round(cur + 0.2, 1)
        if nxt > 2.0:
            nxt = 0.6
        s["audio"]["mic_gain"] = nxt
        save_settings(s)
        return f"Mic gain = {nxt:.1f}x."
    if key == "stt_provider":
        opts = ["auto", "gemini_live", "whisper", "none"]
        cur = s["voice"].get("stt_provider", "auto")
        s["voice"]["stt_provider"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else "auto"
        save_settings(s)
        return f"STT provider = {s['voice']['stt_provider']}."
    if key == "tts_provider":
        opts = ["system", "piper", "elevenlabs", "none"]
        cur = s["voice"].get("tts_provider", "system")
        s["voice"]["tts_provider"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else "system"
        save_settings(s)
        return f"TTS provider = {s['voice']['tts_provider']}."
    if key == "voice_name":
        val = prompt_fn("Voice profile name (e.g. en-gb): ")
        if val:
            s["voice"]["voice_name"] = val
            save_settings(s)
            return f"Voice profile = {val}."
        return "Unchanged."
    if key == "auto_speak":
        s["voice"]["auto_speak"] = not s["voice"]["auto_speak"]
        save_settings(s)
        return f"Auto-speak = {s['voice']['auto_speak']}."
    if key == "wakeword_enabled":
        ww = s.setdefault("wakeword", {})
        ww["enabled"] = not bool(ww.get("enabled", False))
        save_settings(s)
        return f"Wake word ('{ww.get('phrase', 'hey dex')}') = {'ENABLED' if ww['enabled'] else 'DISABLED'}."
    if key == "wakeword_threshold":
        ww = s.setdefault("wakeword", {})
        opts = [0.35, 0.50, 0.65, 0.80]
        cur = round(float(ww.get("threshold", 0.5)), 2)
        ww["threshold"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 0.50
        save_settings(s)
        return f"Wake word threshold = {ww['threshold']:.2f}."
    if key == "wakeword_model_path":
        val = prompt_fn("openWakeWord model path (default providers/wakewords/hey_dex.onnx): ")
        if val:
            s.setdefault("wakeword", {})["model_path"] = val
            save_settings(s)
            return f"Wake model = {val}."
        return "Unchanged."
    if key == "ai_provider":
        s["ai"]["provider"] = "openai" if s["ai"].get("provider") == "gemini" else "gemini"
        save_settings(s)
        return f"AI provider = {s['ai']['provider']}."
    if key == "gemini_model":
        opts = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
        cur = s["ai"].get("gemini_model", "gemini-2.5-flash")
        s["ai"]["gemini_model"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else "gemini-2.5-flash"
        save_settings(s)
        return f"Gemini model = {s['ai']['gemini_model']}."
    if key == "openai_model":
        val = prompt_fn("OpenAI-compatible model name: ")
        if val:
            s["ai"]["openai_model"] = val
            save_settings(s)
            return f"OpenAI model = {val}."
        return "Unchanged."
    if key in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
        val = prompt_fn(f"Enter {key} (blank to cancel, '-' to clear): ")
        if val == "-":
            save_api_key(key, "")
            return f"Cleared {key}."
        if val:
            save_api_key(key, val)
            return f"Saved {key} ({mask_key(val)})."
        return "Unchanged."
    if key.startswith("plug:"):
        fname = key.split(":", 1)[1]
        _en, msg = toggle_plugin(fname)
        return msg
    if key.startswith("act:"):
        fname = key.split(":", 1)[1]
        _en, msg = toggle_action(fname)
        return msg
    if key == "tick_ms":
        opts = [120, 180, 300]
        cur = int(s["performance"].get("tick_ms", 180))
        s["performance"]["tick_ms"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 180
        save_settings(s)
        return f"Render tick = {s['performance']['tick_ms']} ms."
    if key == "bg_sched":
        s["performance"]["background_scheduler"] = not s["performance"]["background_scheduler"]
        save_settings(s)
        return f"Background scheduler = {s['performance']['background_scheduler']}."
    if key == "create_backup":
        path = export_config_backup("settings")
        return f"Saved backup: {path.name}"
    if key.startswith("restore:"):
        bname = key.split(":", 1)[1]
        target = next((b for b in list_config_backups() if b.name == bname), None)
        if target and restore_config_backup(target):
            return f"Restored config from {bname}."
        return f"Restore failed for {bname}."
    return "No action bound to this setting."


def run_tui(
    dispatch_fn: Callable[[str], dict[str, Any]],
    snapshot_fn: Callable[[], dict[str, Any]],
    arch_fn: Callable[[], dict[str, Any]],
    ai_fn: Callable[[str, str, list[dict[str, str]] | None], tuple[str, list[str]]],
    system_prompt_fn: Callable[[int, int], str] | None = None,
) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(render_startup_screen(snapshot_fn(), arch_fn()))
        return

    screen = 0  # 0=startup, 1=dashboard, 2=chat, 3=plugins/actions, 4=memory/tasks/routines
    prev_screen = 1
    show_settings = False
    show_voice = False

    module_tab = "plugins"
    module_detail = False
    selected_module = 0

    memory_tab = "memory"
    selected_mem_item = 0
    memory_filter = ""

    settings_cat_idx = 0
    settings_opt_idx = 0
    settings_note = ""

    history_log: list[str] = [f"{GREEN}[ONLINE]{BG_RESET} DEX // AURA TERMINAL initialized."]
    transcript: list[str] = []
    chat_history: list[dict[str, str]] = []
    diag_lines: list[str] = dispatch_fn("diag").get("lines", [])

    waveform_bars: list[int] = [0] * 24
    voice_events: list[str] = []
    voice_state = "IDLE"

    def _get_sys_prompt() -> str:
        a = arch_fn()
        if system_prompt_fn:
            return system_prompt_fn(len(a.get("actions", [])), len(a.get("plugins", [])))
        return "You are DEX running in AURA TERMINAL."

    def _on_voice_event(ev: LiveEvent) -> None:
        nonlocal voice_state
        if ev.text:
            voice_events.append(ev.text)
            history_log.append(f"{AMBER if ev.kind == 'error' else GREEN}[VOICE]{BG_RESET} {ev.text[:72]}")
        if ev.kind == "done":
            voice_state = "IDLE"

    def _on_waveform(bars: list[int]) -> None:
        nonlocal waveform_bars
        waveform_bars = bars

    voice_session = GeminiLiveVoiceSession(
        dispatch_fn=dispatch_fn,
        system_prompt_fn=_get_sys_prompt,
        tool_registry={},
        on_event=_on_voice_event,
        on_waveform=_on_waveform,
    )

    def _on_wake_detected(score: float, label: str) -> None:
        nonlocal show_voice, show_settings
        show_voice = True
        show_settings = False
        voice_events.append(f"Wake word '{label}' detected (score={score:.2f}) -> Listening...")
        ok_w, msg_w = voice_session.start_listening()
        if not ok_w:
            voice_events.append(msg_w)

    def _sync_wakeword() -> None:
        if load_settings().get("wakeword", {}).get("enabled", False):
            ok_ww, msg_ww = voice_session.arm_wakeword(on_wake=_on_wake_detected)
            if not ok_ww:
                voice_events.append(msg_ww)
        else:
            voice_session.disarm_wakeword()

    _sync_wakeword()

    scheduler = RoutineScheduler(
        dispatch_fn=dispatch_fn,
        on_notify=lambda msg: history_log.append(f"{AMBER}[ROUTINE]{BG_RESET} {msg}"),
    )
    scheduler.start()

    old_termios = None
    if os.name != "nt":
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_termios = termios.tcgetattr(fd)
        tty.setraw(fd)

    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()

    frame_idx = 0
    last_telemetry_ts = 0.0
    telemetry = snapshot_fn()
    arch = arch_fn()

    try:
        while True:
            s = load_settings()
            now = time.monotonic()
            telem_interval = float(s["performance"].get("telemetry_interval_s", 2.0))
            if now - last_telemetry_ts >= telem_interval:
                telemetry = snapshot_fn()
                arch = arch_fn()
                last_telemetry_ts = now

            w = get_term_width()
            v_state = voice_session.state_label if voice_session else voice_state

            sys.stdout.write("\033[H\033[J")
            if show_voice:
                sys.stdout.write(
                    render_voice_screen(
                        telemetry,
                        arch,
                        w,
                        voice_state=v_state,
                        waveform_bars=waveform_bars,
                        transcript=voice_session.last_transcript,
                        response=voice_session.last_response,
                        voice_events=voice_events,
                        frame_idx=frame_idx,
                    )
                )
            elif show_settings:
                sys.stdout.write(
                    render_settings_screen(
                        telemetry,
                        arch,
                        settings_cat_idx,
                        settings_opt_idx,
                        w,
                        status_note=settings_note,
                        frame_idx=frame_idx,
                        voice_state=v_state,
                    )
                )
            elif screen == 0:
                sys.stdout.write(render_startup_screen(telemetry, arch, w, frame_idx=frame_idx))
            elif screen == 1:
                sys.stdout.write(
                    render_dashboard(
                        telemetry,
                        arch,
                        history_log,
                        w,
                        frame_idx=frame_idx,
                        waveform_bars=waveform_bars,
                        voice_state=v_state,
                    )
                )
            elif screen == 2:
                sys.stdout.write(render_chat_screen(telemetry, transcript, w, frame_idx=frame_idx, voice_state=v_state))
            elif screen == 3:
                sys.stdout.write(
                    render_plugins_screen(
                        telemetry,
                        arch,
                        selected_module,
                        w,
                        module_tab=module_tab,
                        show_detail=module_detail,
                        frame_idx=frame_idx,
                        voice_state=v_state,
                    )
                )
            elif screen == 4:
                sys.stdout.write(
                    render_memory_screen(
                        telemetry,
                        arch,
                        selected_mem_item,
                        w,
                        sub_tab=memory_tab,
                        search_query=memory_filter,
                        diag_lines=diag_lines,
                        frame_idx=frame_idx,
                        voice_state=v_state,
                    )
                )
            sys.stdout.flush()

            tick_s = max(0.08, float(s["performance"].get("tick_ms", 180)) / 1000.0)
            key = _read_key_nonblocking(tick_s)
            frame_idx += 1
            if key is None:
                continue

            if key in ("\x03",):
                break

            # CTRL+SPACE (\x00) or CTRL+G (\x07) toggles Voice Listening
            if key in ("\x00", "\x07"):
                show_voice = True
                show_settings = False
                if voice_session.listening:
                    voice_session.stop_and_process()
                else:
                    ok, msg = voice_session.start_listening()
                    if not ok:
                        voice_events.append(msg)
                continue

            if show_voice:
                if key in ("\033", "q", "Q"):
                    if voice_session.listening:
                        voice_session.stop_and_process()
                    show_voice = False
                    if key in ("q", "Q"):
                        break
                elif key in ("w", "W"):
                    s_cur = load_settings()
                    ww = s_cur.setdefault("wakeword", {})
                    ww["enabled"] = not bool(ww.get("enabled", False))
                    save_settings(s_cur)
                    _sync_wakeword()
                    arch = arch_fn()
                elif key in ("s", "S"):
                    show_voice = False
                    show_settings = True
                    settings_cat_idx = 5  # jump to Voice Preferences
                    settings_opt_idx = 0
                continue

            if key in ("q", "Q"):
                break

            # Settings Toggle [S]
            if key in ("s", "S"):
                if show_settings:
                    show_settings = False
                else:
                    prev_screen = screen if screen > 0 else 1
                    show_settings = True
                    settings_note = ""
                continue

            if show_settings:
                cat_id, _ = SETTINGS_CATEGORIES[settings_cat_idx % len(SETTINGS_CATEGORIES)]
                items = _settings_items_for_category(cat_id, arch)
                if key == "\033":
                    show_settings = False
                elif key in ("\033[C", "l", "L"):
                    settings_cat_idx = (settings_cat_idx + 1) % len(SETTINGS_CATEGORIES)
                    settings_opt_idx = 0
                    settings_note = ""
                elif key in ("\033[D", "h", "H"):
                    settings_cat_idx = (settings_cat_idx - 1) % len(SETTINGS_CATEGORIES)
                    settings_opt_idx = 0
                    settings_note = ""
                elif key in ("\033[B", "j", "J") and items:
                    settings_opt_idx = (settings_opt_idx + 1) % len(items)
                elif key in ("\033[A", "k", "K") and items:
                    settings_opt_idx = (settings_opt_idx - 1) % len(items)
                elif key in ("\r", "\n", " ") and items:
                    chosen = items[settings_opt_idx % len(items)]
                    settings_note = _apply_setting_action(
                        chosen["key"],
                        lambda p: _prompt_line(p, old_termios),
                    )
                    if chosen["key"].startswith("wakeword_"):
                        _sync_wakeword()
                    arch = arch_fn()
                    history_log.append(f"{GREEN}[SETTINGS]{BG_RESET} {settings_note}")
                continue

            if screen == 0:
                if key in ("\r", "\n"):
                    screen = 1
                elif key in ("1", "2", "3", "4"):
                    screen = int(key)
                continue

            if key in ("1", "2", "3", "4"):
                screen = int(key)
                continue

            if key in ("d", "D"):
                diag_lines = dispatch_fn("diag").get("lines", [])
                history_log.append(f"{GREEN}[DIAG]{BG_RESET} Diagnostic sweep completed.")
                screen = 4
                memory_tab = "routines"
                continue

            # Screen 3: Plugins & Actions Manager
            if screen == 3:
                active_list = arch.get("all_plugins", []) if module_tab == "plugins" else arch.get("all_actions", [])
                if key == "\t":
                    module_tab = "actions" if module_tab == "plugins" else "plugins"
                    selected_module = 0
                    continue
                if key in ("\033[A", "k", "K") and active_list:
                    selected_module = (selected_module - 1) % len(active_list)
                    continue
                if key in ("\033[B", "j", "J") and active_list:
                    selected_module = (selected_module + 1) % len(active_list)
                    continue
                if key in ("i", "I"):
                    module_detail = not module_detail
                    continue
                if key == " " and active_list:
                    sel = active_list[selected_module % len(active_list)]
                    if module_tab == "plugins":
                        _en, msg = toggle_plugin(sel["filename"])
                    else:
                        _en, msg = toggle_action(sel["filename"])
                    history_log.append(f"{GREEN}[MODULE]{BG_RESET} {msg}")
                    arch = arch_fn()
                    continue
                if key in ("a", "A") and module_tab == "plugins" and active_list:
                    sel = active_list[selected_module % len(active_list)]
                    msg = approve_plugin(sel["filename"])
                    history_log.append(f"{GREEN}[SECURITY]{BG_RESET} {msg}")
                    arch = arch_fn()
                    continue
                if key in ("r", "R"):
                    arch = arch_fn()
                    history_log.append(f"{GREEN}[RELOAD]{BG_RESET} Reloaded {len(arch['actions'])} actions & {len(arch['plugins'])} plugins.")
                    continue
                if key in ("t", "T"):
                    res = dispatch_fn("test providers")
                    transcript.extend([f"{WHITE}{ln}{BG_RESET}" for ln in res.get("lines", [])])
                    screen = 2
                    continue

            # Screen 4: Memory, Tasks & Routines
            if screen == 4:
                if key == "\t":
                    order = ["memory", "tasks", "routines"]
                    memory_tab = order[(order.index(memory_tab) + 1) % len(order)]
                    selected_mem_item = 0
                    continue
                if memory_tab == "memory":
                    facts = search_facts(memory_filter) if memory_filter else load_memory().get("facts", [])
                    if key in ("\033[A", "k", "K") and facts:
                        selected_mem_item = (selected_mem_item - 1) % len(facts)
                        continue
                    if key in ("\033[B", "j", "J") and facts:
                        selected_mem_item = (selected_mem_item + 1) % len(facts)
                        continue
                    if key in ("n", "N"):
                        txt = _prompt_line("New memory fact: ", old_termios)
                        if txt:
                            entry = add_fact(txt)
                            history_log.append(f"{GREEN}[MEMORY]{BG_RESET} Stored {entry['id']}")
                        continue
                    if key in ("f", "F"):
                        memory_filter = _prompt_line("Search memory (blank resets): ", old_termios)
                        selected_mem_item = 0
                        continue
                    if key in ("c", "C"):
                        memory_filter = ""
                        selected_mem_item = 0
                        continue
                    if key in ("x", "X") and facts:
                        sel = facts[selected_mem_item % len(facts)]
                        removed = remove_fact(sel["id"])
                        if removed:
                            history_log.append(f"{AMBER}[MEMORY]{BG_RESET} Removed {removed['id']}")
                            selected_mem_item = max(0, selected_mem_item - 1)
                        continue
                elif memory_tab == "tasks":
                    tasks = arch.get("tasks", [])
                    if key in ("\033[A", "k", "K") and tasks:
                        selected_mem_item = (selected_mem_item - 1) % len(tasks)
                        continue
                    if key in ("\033[B", "j", "J") and tasks:
                        selected_mem_item = (selected_mem_item + 1) % len(tasks)
                        continue
                    if key in ("n", "N"):
                        goal = _prompt_line("New task goal: ", old_termios)
                        if goal:
                            t_created = start_task(goal)
                            history_log.append(f"{GREEN}[TASK]{BG_RESET} Started {t_created['id']}")
                            arch = arch_fn()
                        continue
                    if key in ("w", "W") and tasks:
                        sel = tasks[selected_mem_item % len(tasks)]
                        note = _prompt_line(f"Steer {sel['id']}: ", old_termios)
                        if note:
                            steer_task(sel["id"], note)
                            history_log.append(f"{GREEN}[TASK]{BG_RESET} Steered {sel['id']}")
                            arch = arch_fn()
                        continue
                    if key in ("u", "U") and tasks:
                        sel = tasks[selected_mem_item % len(tasks)]
                        resume_task(sel["id"])
                        history_log.append(f"{GREEN}[TASK]{BG_RESET} Resumed {sel['id']}")
                        arch = arch_fn()
                        continue
                    if key in ("x", "X") and tasks:
                        sel = tasks[selected_mem_item % len(tasks)]
                        cancel_task(sel["id"])
                        history_log.append(f"{AMBER}[TASK]{BG_RESET} Cancelled {sel['id']}")
                        arch = arch_fn()
                        continue
                else:
                    routines = arch.get("routines", [])
                    if key in ("\033[A", "k", "K") and routines:
                        selected_mem_item = (selected_mem_item - 1) % len(routines)
                        continue
                    if key in ("\033[B", "j", "J") and routines:
                        selected_mem_item = (selected_mem_item + 1) % len(routines)
                        continue
                    if key in ("r", "R") and routines:
                        sel = routines[selected_mem_item % len(routines)]
                        mark_routine_run(sel["name"])
                        res = dispatch_fn(sel.get("command", "status"))
                        diag_lines = res.get("lines", [])
                        history_log.append(f"{GREEN}[ROUTINE]{BG_RESET} Ran '{sel['name']}'")
                        arch = arch_fn()
                        continue
                    if key in ("h", "H"):
                        diag_lines = dispatch_fn("protocol house_party").get("lines", [])
                        history_log.append(f"{GREEN}[PROTOCOL]{BG_RESET} House Party engaged.")
                        continue
                    if key in ("u", "U"):
                        diag_lines = dispatch_fn("undo").get("lines", [])
                        continue

            if key in ("r", "R") and screen == 1:
                telemetry = snapshot_fn()
                arch = arch_fn()
                history_log.append(f"{GREEN}[SYNC]{BG_RESET} Telemetry refreshed at {time.strftime('%H:%M:%S')}")
                continue

            if key in ("c", "C") and screen == 2:
                transcript.clear()
                chat_history.clear()
                continue

            if key in ("/", "\r", "\n"):
                cmd_input = _prompt_line("dex@mark57:~$ ", old_termios)
                if not cmd_input:
                    continue
                if cmd_input.lower() in ("exit", "quit"):
                    break
                transcript.append(f"{WHITE}YOU > {cmd_input}{BG_RESET}")
                res = dispatch_fn(cmd_input)
                if res["mode"] == "local":
                    for ln in res.get("lines", []):
                        transcript.append(f"{SLATE}{ln}{BG_RESET}")
                    history_log.append(f"{GREEN}[CMD]{BG_RESET} {cmd_input}")
                    arch = arch_fn()
                else:
                    reply, traces = ai_fn(res["query"], res["system_prompt"], chat_history)
                    for tr in traces:
                        transcript.append(f"{AMBER}{tr}{BG_RESET}")
                    for ln in reply.splitlines():
                        transcript.append(f"{WHITE}DEX > {ln}{BG_RESET}")
                    chat_history.append({"role": "user", "text": res["query"]})
                    chat_history.append({"role": "assistant", "text": reply})
                    history_log.append(f"{GREEN}[AI]{BG_RESET} {cmd_input[:44]}")
                screen = 2

    finally:
        scheduler.stop()
        voice_session.disarm_wakeword()
        if voice_session.listening:
            voice_session.stop_and_process()
        if old_termios is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_termios)
        sys.stdout.write("\033[?25h\033[?1049l\n")
        sys.stdout.flush()
