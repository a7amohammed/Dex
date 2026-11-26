"""Linux distro, terminal capability, and audio stack detection for DEX (Mark LVII)."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from core.lazyimport import is_available

SUPPORTED_DISTROS = {
    "zorin": "Zorin OS",
    "ubuntu": "Ubuntu",
    "linuxmint": "Linux Mint",
    "debian": "Debian",
    "fedora": "Fedora",
    "arch": "Arch Linux",
    "endeavouros": "EndeavourOS",
    "opensuse": "openSUSE",
    "opensuse-tumbleweed": "openSUSE Tumbleweed",
    "opensuse-leap": "openSUSE Leap",
}


def parse_os_release(content: str | None = None) -> dict[str, str]:
    if content is None:
        os_rel = Path("/etc/os-release")
        if not os_rel.exists():
            return {"id": platform.system().lower(), "pretty_name": platform.platform(), "id_like": ""}
        content = os_rel.read_text(encoding="utf-8", errors="replace")

    info: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        info[k.strip().lower()] = v.strip().strip('"').strip("'")

    raw_id = info.get("id", "linux").lower()
    if raw_id.startswith("opensuse"):
        matched = SUPPORTED_DISTROS.get(raw_id, "openSUSE")
    else:
        matched = SUPPORTED_DISTROS.get(raw_id, info.get("name", raw_id.title()))

    return {
        "id": raw_id,
        "id_like": info.get("id_like", "").lower(),
        "pretty_name": info.get("pretty_name", matched),
        "supported_name": matched,
        "is_supported_linux": raw_id in SUPPORTED_DISTROS or any(
            d in info.get("id_like", "").lower() for d in ("debian", "ubuntu", "fedora", "arch", "suse")
        ),
    }


def detect_display_server() -> str:
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland"
    if os.environ.get("DISPLAY"):
        return "X11"
    return "Headless TTY"


def detect_audio_stack() -> dict[str, Any]:
    bins = {
        "pw_record": shutil.which("pw-record") is not None,
        "pw_play": shutil.which("pw-play") is not None,
        "pactl": shutil.which("pactl") is not None,
        "parecord": shutil.which("parecord") is not None,
        "paplay": shutil.which("paplay") is not None,
        "arecord": shutil.which("arecord") is not None,
        "aplay": shutil.which("aplay") is not None,
        "espeak_ng": shutil.which("espeak-ng") is not None,
        "spd_say": shutil.which("spd-say") is not None,
        "piper": shutil.which("piper") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }
    py_mods = {
        "sounddevice": is_available("sounddevice"),
        "pyaudio": is_available("pyaudio"),
        "numpy": is_available("numpy"),
        "websockets": is_available("websockets"),
        "google_genai": is_available("google.genai"),
        "faster_whisper": is_available("faster_whisper"),
        "openwakeword": is_available("openwakeword"),
    }

    if bins["pw_record"] or bins["pactl"]:
        backend = "PipeWire / PulseAudio"
    elif bins["parecord"]:
        backend = "PulseAudio"
    elif bins["arecord"]:
        backend = "ALSA"
    elif py_mods["sounddevice"] or py_mods["pyaudio"]:
        backend = "PortAudio (Python)"
    else:
        backend = "Unavailable (headless)"

    voice_ready = any([bins["pw_record"], bins["parecord"], bins["arecord"], py_mods["sounddevice"], py_mods["pyaudio"]])
    return {
        "backend": backend,
        "binaries": bins,
        "python_packages": py_mods,
        "voice_capture_ready": voice_ready,
        "tts_ready": any([bins["espeak_ng"], bins["spd_say"], bins["piper"]]),
        "wakeword_ready": bool(voice_ready and py_mods["openwakeword"] and py_mods["numpy"]),
    }


def detect_platform_support() -> dict[str, Any]:
    system = platform.system()
    is_tty = sys.stdout.isatty() and sys.stdin.isatty()
    term = os.environ.get("TERM", "unknown")
    colorterm = os.environ.get("COLORTERM", "")
    truecolor = colorterm in ("truecolor", "24bit") or "256color" in term or is_tty
    distro = parse_os_release() if system == "Linux" else {"id": system.lower(), "pretty_name": platform.platform(), "supported_name": system, "is_supported_linux": False}
    audio = detect_audio_stack()

    return {
        "os": system,
        "release": platform.release(),
        "arch": platform.machine(),
        "distro": distro,
        "display_server": detect_display_server() if system == "Linux" else system,
        "python_version": platform.python_version(),
        "terminal": term,
        "tty": is_tty,
        "ansi_color": truecolor,
        "audio": audio,
        "tools_available": {
            "python3": shutil.which("python3") is not None,
            "git": shutil.which("git") is not None,
            "ffmpeg": audio["binaries"]["ffmpeg"],
        },
        "notes": (
            f"{distro['pretty_name']} ({detect_display_server()}) · Audio: {audio['backend']}"
        ),
    }
