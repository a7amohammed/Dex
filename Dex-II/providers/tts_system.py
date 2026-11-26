"""System TTS provider — Linux espeak-ng/spd-say, macOS say, Windows SAPI."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from providers.base import ProviderCapabilities


class SystemTTSProvider:
    name = "system_tts"
    capabilities = ProviderCapabilities(streaming=False)

    def __init__(self, voice: str = "en-gb") -> None:
        self.voice = voice

    def is_available(self) -> bool:
        sys_name = platform.system()
        if sys_name == "Linux":
            return bool(shutil.which("espeak-ng") or shutil.which("spd-say"))
        if sys_name == "Darwin":
            return bool(shutil.which("say"))
        return sys_name == "Windows"

    def speak(self, text: str) -> tuple[bool, str]:
        clean = text.strip()
        if not clean:
            return False, "Nothing to speak."
        sys_name = platform.system()
        try:
            if sys_name == "Linux":
                if shutil.which("espeak-ng"):
                    subprocess.Popen(["espeak-ng", "-v", self.voice, clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, "Spoken via espeak-ng."
                if shutil.which("spd-say"):
                    subprocess.Popen(["spd-say", clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, "Spoken via spd-say."
                return False, "Install espeak-ng or speech-dispatcher for Linux system speech."
            if sys_name == "Darwin" and shutil.which("say"):
                subprocess.Popen(["say", clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, "Spoken via macOS say."
            if os.name == "nt":
                ps = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean.replace(chr(39), '')}')"
                subprocess.Popen(["powershell", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, "Spoken via Windows SAPI."
        except Exception as exc:
            return False, f"System TTS error: {exc}"
        return False, "System TTS unavailable."
