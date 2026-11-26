"""Audio rates, PCM16 capture/playback, and live terminal waveform math."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import threading
from typing import Callable

from core.audio_devices import list_audio_devices
from core.lazyimport import lazy_import

INPUT_RATE_HZ = 16000
OUTPUT_RATE_HZ = 24000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2


def compute_waveform_bars(pcm16_bytes: bytes, bars: int = 24, gain: float = 1.0) -> list[int]:
    """Compute normalized 0..8 level bars directly from raw signed 16-bit PCM frames."""
    if not pcm16_bytes or len(pcm16_bytes) < 2 or bars <= 0:
        return [0] * max(1, bars)

    usable = len(pcm16_bytes) - (len(pcm16_bytes) % 2)
    count = usable // 2
    samples = struct.unpack(f"<{count}h", pcm16_bytes[:usable])
    chunk = max(1, count // bars)
    levels: list[int] = []
    for i in range(bars):
        seg = samples[i * chunk : (i + 1) * chunk]
        if not seg:
            levels.append(0)
            continue
        rms = math.sqrt(sum(s * s for s in seg) / len(seg)) / 32768.0
        scaled = min(1.0, rms * 4.5 * max(0.2, gain))
        levels.append(int(round(scaled * 8)))
    return levels


def render_waveform_glyphs(levels: list[int]) -> str:
    glyphs = " ▁▂▃▄▅▆▇█"
    return "".join(glyphs[max(0, min(8, lv))] for lv in levels)


class LinuxAudioCapture:
    """Non-blocking 16 kHz PCM16 microphone capture across PipeWire/PulseAudio/ALSA/sounddevice."""

    def __init__(self, device: str = "auto", gain: float = 1.0) -> None:
        self.device = device
        self.gain = gain
        self._stop_event = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._chunks: list[bytes] = []
        self.error: str | None = None
        self.active = False

    def start(self, on_chunk: Callable[[bytes, list[int]], None] | None = None) -> tuple[bool, str]:
        info = list_audio_devices()
        tool = info.get("capture_tool")
        if not tool:
            self.error = "No Linux audio capture backend detected (install pipewire, pulseaudio-utils, alsa-utils, or sounddevice)."
            return False, self.error

        self._stop_event.clear()
        self._chunks.clear()
        self.active = True

        if tool == "sounddevice":
            sd = lazy_import("sounddevice")
            if sd is None:
                self.active = False
                self.error = "sounddevice unavailable."
                return False, self.error

            def _sd_worker() -> None:
                try:
                    dev_arg = int(self.device) if self.device.isdigit() else None
                    with sd.RawInputStream(samplerate=INPUT_RATE_HZ, channels=CHANNELS, dtype="int16", blocksize=1600, device=dev_arg) as stream:
                        while not self._stop_event.is_set():
                            data, _ = stream.read(1600)
                            raw = bytes(data)
                            self._chunks.append(raw)
                            if on_chunk:
                                on_chunk(raw, compute_waveform_bars(raw, gain=self.gain))
                except Exception as exc:
                    self.error = f"Audio input error: {exc}"
                finally:
                    self.active = False

            self._thread = threading.Thread(target=_sd_worker, daemon=True)
            self._thread.start()
            return True, f"Capturing via sounddevice ({INPUT_RATE_HZ} Hz PCM16)"

        cmd = self._build_cli_cmd(tool)
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as exc:
            self.active = False
            self.error = f"Failed to start {tool}: {exc}"
            return False, self.error

        def _proc_worker() -> None:
            assert self._proc is not None and self._proc.stdout is not None
            try:
                while not self._stop_event.is_set():
                    data = self._proc.stdout.read(3200)
                    if not data:
                        break
                    self._chunks.append(data)
                    if on_chunk:
                        on_chunk(data, compute_waveform_bars(data, gain=self.gain))
            except Exception as exc:
                self.error = f"Capture stream error: {exc}"
            finally:
                self.active = False

        self._thread = threading.Thread(target=_proc_worker, daemon=True)
        self._thread.start()
        return True, f"Capturing via {tool} ({INPUT_RATE_HZ} Hz PCM16)"

    def _build_cli_cmd(self, tool: str) -> list[str]:
        if tool == "pw-record":
            cmd = ["pw-record", "--format", "s16", "--rate", str(INPUT_RATE_HZ), "--channels", str(CHANNELS)]
            if self.device != "auto":
                cmd.extend(["--target", self.device])
            cmd.append("-")
            return cmd
        if tool == "parecord":
            cmd = ["parecord", "--raw", "--format=s16le", f"--rate={INPUT_RATE_HZ}", f"--channels={CHANNELS}"]
            if self.device != "auto":
                cmd.append(f"--device={self.device}")
            return cmd
        cmd = ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(INPUT_RATE_HZ), "-c", str(CHANNELS)]
        if self.device != "auto":
            cmd.extend(["-D", self.device])
        return cmd

    def stop(self) -> bytes:
        self._stop_event.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        self.active = False
        return b"".join(self._chunks)


def play_pcm_audio(pcm_bytes: bytes, sample_rate: int = OUTPUT_RATE_HZ) -> tuple[bool, str]:
    if not pcm_bytes:
        return False, "No audio bytes to play."
    if shutil.which("pw-play"):
        cmd = ["pw-play", "--format", "s16", "--rate", str(sample_rate), "--channels", "1", "-"]
    elif shutil.which("paplay"):
        cmd = ["paplay", "--raw", "--format=s16le", f"--rate={sample_rate}", "--channels=1"]
    elif shutil.which("aplay"):
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(sample_rate), "-c", "1"]
    else:
        return False, "No Linux audio playback binary found (pw-play / paplay / aplay)."

    try:
        subprocess.run(cmd, input=pcm_bytes, timeout=20, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Playback finished."
    except Exception as exc:
        return False, f"Playback error: {exc}"
