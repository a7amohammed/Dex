"""Local openWakeWord ('hey dex') wake-word detector and passive microphone listener."""

from __future__ import annotations

import struct
import time
from pathlib import Path
from typing import Any, Callable

from core.lazyimport import is_available, lazy_import
from providers.audio import LinuxAudioCapture
from providers.base import ProviderCapabilities

BASE_DIR = Path(__file__).resolve().parent.parent
WAKEWORDS_DIR = Path(__file__).resolve().parent / "wakewords"


class OpenWakeWordProvider:
    """Detects the 'hey dex' wake phrase on 16 kHz PCM16 mono audio frames via openWakeWord."""

    name = "openwakeword"
    capabilities = ProviderCapabilities(streaming=True, tool_calling=False)

    def __init__(
        self,
        phrase: str = "hey dex",
        model_path: str = "providers/wakewords/hey_dex.onnx",
        threshold: float = 0.5,
        cooldown_s: float = 2.0,
        inference_framework: str = "onnx",
        model: Any = None,
    ) -> None:
        self.phrase = phrase
        self.model_path = model_path
        self.threshold = float(threshold)
        self.cooldown_s = float(cooldown_s)
        self.inference_framework = inference_framework
        self._model = model
        self._last_trigger_ts = 0.0
        self.last_score = 0.0
        self.last_label = ""
        self.last_error: str | None = None

    def resolve_model_path(self) -> Path | None:
        if not self.model_path:
            return None
        candidate = Path(self.model_path)
        if not candidate.is_absolute():
            candidate = BASE_DIR / candidate
        if candidate.exists():
            return candidate
        # Fallback: check common filenames inside providers/wakewords/
        for ext in ("onnx", "tflite"):
            alt = WAKEWORDS_DIR / f"hey_dex.{ext}"
            if alt.exists():
                return alt
        return None

    def availability_detail(self) -> dict[str, Any]:
        oww_ok = is_available("openwakeword")
        np_ok = is_available("numpy")
        resolved = self.resolve_model_path()
        injected = self._model is not None

        if injected:
            ready = True
            reason = "Custom/injected wake-word model active."
        elif not oww_ok:
            ready = False
            reason = "Python package 'openwakeword' is not installed (`pip install openwakeword`)."
        elif not np_ok:
            ready = False
            reason = "Python package 'numpy' is required for openWakeWord audio buffers."
        elif resolved is None:
            ready = False
            reason = (
                f"Wake-word model not found at '{self.model_path}'. "
                "Place your trained 'hey_dex.onnx' or 'hey_dex.tflite' in Dex-II/providers/wakewords/."
            )
        else:
            ready = True
            reason = f"Ready ({resolved.name}, framework={self.inference_framework})"

        return {
            "provider": self.name,
            "phrase": self.phrase,
            "package_installed": oww_ok,
            "numpy_installed": np_ok,
            "model_path": str(resolved) if resolved else self.model_path,
            "model_found": resolved is not None,
            "threshold": self.threshold,
            "ready": ready,
            "reason": reason,
        }

    def is_available(self) -> bool:
        return bool(self.availability_detail()["ready"])

    def load_model(self) -> tuple[bool, str]:
        if self._model is not None:
            return True, f"openWakeWord model loaded for '{self.phrase}'."
        detail = self.availability_detail()
        if not detail["ready"]:
            self.last_error = detail["reason"]
            return False, detail["reason"]

        oww_model_mod = lazy_import("openwakeword.model")
        if oww_model_mod is None or not hasattr(oww_model_mod, "Model"):
            self.last_error = "openwakeword.model.Model could not be imported."
            return False, self.last_error

        model_file = self.resolve_model_path()
        try:
            self._model = oww_model_mod.Model(
                wakeword_models=[str(model_file)],
                inference_framework=self.inference_framework,
            )
            self.last_error = None
            return True, f"Loaded openWakeWord model '{model_file.name}' for '{self.phrase}'."
        except Exception as exc:
            self.last_error = f"Failed to initialize openWakeWord model: {exc}"
            return False, self.last_error

    def _decode_pcm16(self, pcm16_bytes: bytes) -> Any:
        np = lazy_import("numpy")
        if np is not None:
            usable = len(pcm16_bytes) - (len(pcm16_bytes) % 2)
            return np.frombuffer(pcm16_bytes[:usable], dtype=np.int16)
        usable = len(pcm16_bytes) - (len(pcm16_bytes) % 2)
        count = usable // 2
        return list(struct.unpack(f"<{count}h", pcm16_bytes[:usable]))

    def process_pcm16(self, pcm16_bytes: bytes, now_ts: float | None = None) -> tuple[bool, float, str]:
        """Run openWakeWord inference on 16 kHz mono PCM16 bytes. Returns (triggered, score, label)."""
        if not pcm16_bytes or len(pcm16_bytes) < 2:
            return False, 0.0, ""
        if self._model is None:
            ok, _msg = self.load_model()
            if not ok:
                return False, 0.0, ""

        samples = self._decode_pcm16(pcm16_bytes)
        prediction = self._model.predict(samples)
        if not isinstance(prediction, dict) or not prediction:
            return False, 0.0, ""

        best_label = ""
        best_score = 0.0
        for label, score in prediction.items():
            try:
                val = float(score)
            except (TypeError, ValueError):
                continue
            if val >= best_score:
                best_score = val
                best_label = str(label)

        self.last_score = best_score
        self.last_label = best_label

        ref_ts = time.monotonic() if now_ts is None else now_ts
        if best_score >= self.threshold and (ref_ts - self._last_trigger_ts) >= self.cooldown_s:
            self._last_trigger_ts = ref_ts
            return True, best_score, best_label
        return False, best_score, best_label


class WakeWordListener:
    """Background 16 kHz microphone monitor waiting for 'hey dex' before handing off to voice chat."""

    def __init__(
        self,
        provider: OpenWakeWordProvider,
        on_detected: Callable[[float, str], None],
        on_status: Callable[[str], None] | None = None,
        device: str = "auto",
        gain: float = 1.0,
    ) -> None:
        self.provider = provider
        self.on_detected = on_detected
        self.on_status = on_status
        self.device = device
        self.gain = gain
        self.active = False
        self.state_label = "OFF"
        self._capture: LinuxAudioCapture | None = None

    def start(self) -> tuple[bool, str]:
        if self.active:
            return True, f"Wake word '{self.provider.phrase}' already armed."
        ok_model, msg_model = self.provider.load_model()
        if not ok_model:
            self.state_label = "UNAVAILABLE"
            if self.on_status:
                self.on_status(msg_model)
            return False, msg_model

        self._capture = LinuxAudioCapture(device=self.device, gain=self.gain)

        def _on_chunk(raw: bytes, _bars: list[int]) -> None:
            if not self.active:
                return
            triggered, score, label = self.provider.process_pcm16(raw)
            if triggered:
                self.state_label = "TRIGGERED"
                self.stop()
                self.on_detected(score, label or self.provider.phrase)

        ok_cap, msg_cap = self._capture.start(on_chunk=_on_chunk)
        if not ok_cap:
            self.state_label = "MIC UNAVAILABLE"
            if self.on_status:
                self.on_status(msg_cap)
            return False, msg_cap

        self.active = True
        self.state_label = f"ARMED ({self.provider.phrase.upper()})"
        if self.on_status:
            self.on_status(f"Wake word '{self.provider.phrase}' armed ({msg_cap})")
        return True, f"Wake word '{self.provider.phrase}' armed."

    def stop(self) -> None:
        self.active = False
        if self._capture is not None:
            self._capture.stop()
            self._capture = None
        if self.state_label.startswith("ARMED"):
            self.state_label = "OFF"
