"""Linux & cross-platform audio input/output device probing for DEX (Mark LVII)."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from core.lazyimport import lazy_import


def list_audio_devices() -> dict[str, Any]:
    inputs: list[dict[str, str]] = []
    outputs: list[dict[str, str]] = []
    backend = "unavailable"

    sd = lazy_import("sounddevice")
    if sd is not None:
        try:
            backend = "sounddevice"
            for idx, dev in enumerate(sd.query_devices()):
                name = str(dev.get("name", f"Device {idx}"))
                if int(dev.get("max_input_channels", 0)) > 0:
                    inputs.append({"id": str(idx), "name": name, "backend": "PortAudio"})
                if int(dev.get("max_output_channels", 0)) > 0:
                    outputs.append({"id": str(idx), "name": name, "backend": "PortAudio"})
        except Exception:
            pass

    if not inputs and shutil.which("pactl"):
        backend = "PipeWire/PulseAudio (pactl)"
        for kind, target in (("sources", inputs), ("sinks", outputs)):
            try:
                out = subprocess.check_output(["pactl", "list", "short", kind], text=True, timeout=2, stderr=subprocess.DEVNULL)
                for line in out.splitlines():
                    cols = line.split("\t")
                    if len(cols) >= 2 and ".monitor" not in cols[1]:
                        target.append({"id": cols[0], "name": cols[1], "backend": "PipeWire/Pulse"})
            except Exception:
                pass

    if not inputs and shutil.which("arecord"):
        backend = "ALSA"
        try:
            out = subprocess.check_output(["arecord", "-l"], text=True, timeout=2, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if line.startswith("card "):
                    inputs.append({"id": line.split(":", 1)[0].strip(), "name": line.strip(), "backend": "ALSA"})
        except Exception:
            pass

    if not outputs and shutil.which("aplay"):
        try:
            out = subprocess.check_output(["aplay", "-l"], text=True, timeout=2, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if line.startswith("card "):
                    outputs.append({"id": line.split(":", 1)[0].strip(), "name": line.strip(), "backend": "ALSA"})
        except Exception:
            pass

    return {
        "backend": backend,
        "inputs": inputs,
        "outputs": outputs,
        "capture_tool": (
            "pw-record" if shutil.which("pw-record") else
            ("parecord" if shutil.which("parecord") else
             ("arecord" if shutil.which("arecord") else ("sounddevice" if sd is not None else None)))
        ),
        "playback_tool": (
            "pw-play" if shutil.which("pw-play") else
            ("paplay" if shutil.which("paplay") else
             ("aplay" if shutil.which("aplay") else ("sounddevice" if sd is not None else None)))
        ),
    }
