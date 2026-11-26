"""Local neural Piper TTS adapter."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from providers.audio import play_pcm_audio
from providers.base import ProviderCapabilities

BASE_DIR = Path(__file__).resolve().parent


class PiperTTSProvider:
    name = "piper_tts"
    capabilities = ProviderCapabilities(streaming=False, audio_out_hz=22050)

    def __init__(self, model_path: str | None = None) -> None:
        self.voices_dir = BASE_DIR / "voices"
        self.model_path = model_path or self._find_default_model()

    def _find_default_model(self) -> str | None:
        if not self.voices_dir.exists():
            return None
        models = sorted(self.voices_dir.glob("*.onnx"))
        return str(models[0]) if models else None

    def is_available(self) -> bool:
        return bool(shutil.which("piper") and self.model_path and Path(self.model_path).exists())

    def speak(self, text: str) -> tuple[bool, str]:
        if not shutil.which("piper"):
            return False, "Piper binary not found in PATH."
        if not self.model_path or not Path(self.model_path).exists():
            return False, f"No Piper .onnx voice model found in {self.voices_dir}."
        try:
            proc = subprocess.run(
                ["piper", "--model", self.model_path, "--output-raw"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
                check=True,
            )
            return play_pcm_audio(proc.stdout, sample_rate=22050)
        except Exception as exc:
            return False, f"Piper TTS error: {exc}"
