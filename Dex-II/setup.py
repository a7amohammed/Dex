#!/usr/bin/env python3
"""OS & Linux-distro aware setup and capability inspector for DEX // Mark LVII AURA TERMINAL."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.platform_support import detect_platform_support  # noqa: E402

MIN_PYTHON = (3, 10)

DISTRO_AUDIO_HINTS = {
    "zorin": "sudo apt update && sudo apt install -y pipewire-audio pulseaudio-utils alsa-utils espeak-ng",
    "ubuntu": "sudo apt update && sudo apt install -y pipewire-audio pulseaudio-utils alsa-utils espeak-ng",
    "linuxmint": "sudo apt update && sudo apt install -y pipewire-audio pulseaudio-utils alsa-utils espeak-ng",
    "debian": "sudo apt update && sudo apt install -y pipewire-audio pulseaudio-utils alsa-utils espeak-ng",
    "fedora": "sudo dnf install -y pipewire-utils pulseaudio-utils alsa-utils espeak-ng",
    "arch": "sudo pacman -S --needed pipewire pipewire-pulse alsa-utils espeak-ng",
    "endeavouros": "sudo pacman -S --needed pipewire pipewire-pulse alsa-utils espeak-ng",
    "opensuse": "sudo zypper install -y pipewire-tools pulseaudio-utils alsa-utils espeak-ng",
}


def _distro_install_hint(distro_id: str, id_like: str) -> str:
    if distro_id in DISTRO_AUDIO_HINTS:
        return DISTRO_AUDIO_HINTS[distro_id]
    if distro_id.startswith("opensuse"):
        return DISTRO_AUDIO_HINTS["opensuse"]
    for family, cmd in (
        ("ubuntu", DISTRO_AUDIO_HINTS["ubuntu"]),
        ("debian", DISTRO_AUDIO_HINTS["debian"]),
        ("fedora", DISTRO_AUDIO_HINTS["fedora"]),
        ("arch", DISTRO_AUDIO_HINTS["arch"]),
        ("suse", DISTRO_AUDIO_HINTS["opensuse"]),
    ):
        if family in id_like:
            return cmd
    return "Install PipeWire/PulseAudio or ALSA utilities (arecord/aplay) + espeak-ng via your OS package manager."


def check_environment() -> int:
    print("DEX // MARK LVII — AURA TERMINAL ENVIRONMENT CHECK")
    print("=" * 64)
    print(f"Python Runtime : {platform.python_version()} ({platform.system()} {platform.machine()})")
    if sys.version_info < MIN_PYTHON:
        print(f"ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required.")
        return 1

    for folder in ("memory/tasks", "reports", "config/backups", "providers/voices", "providers/wakewords"):
        (base / folder if (base := BASE_DIR) else Path(folder)).mkdir(parents=True, exist_ok=True)

    plat = detect_platform_support()
    distro = plat["distro"]
    audio = plat["audio"]
    print(f"Linux Distro   : {distro.get('pretty_name')} (id={distro.get('id')}, supported={distro.get('is_supported_linux')})")
    print(f"Display Server : {plat['display_server']}   TTY={plat['tty']}   TrueColor/ANSI={plat['ansi_color']}")
    print(f"Audio Backend  : {audio['backend']}")
    print(f"Voice Ready    : capture={audio['voice_capture_ready']}   tts={audio['tts_ready']}   wakeword={audio.get('wakeword_ready', False)}")
    print("")
    print("Core Terminal UI requires Python standard library ONLY (0 mandatory external packages).")
    if not audio["voice_capture_ready"] or not audio["tts_ready"]:
        print("")
        print("Optional Linux Voice / Audio System Packages:")
        print(f"  {_distro_install_hint(distro.get('id', ''), distro.get('id_like', ''))}")
    print("")
    print("Optional Python Packages for Gemini Live, Local Whisper STT & openWakeWord ('hey dex'):")
    print("  pip install google-genai websockets sounddevice faster-whisper openwakeword onnxruntime numpy")
    print("  Place 'hey_dex.onnx' in Dex-II/providers/wakewords/ to activate wake-word detection.")
    print("")
    print("Verification & Launch:")
    print("  python3 -m providers._tests")
    print("  python3 main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_environment())
