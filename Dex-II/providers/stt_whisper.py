"""Speech-to-Text provider — faster-whisper on CPU or OpenAI transcription API."""

from __future__ import annotations

import io
import json
import os
import urllib.request
import wave
from typing import Any

from core.lazyimport import lazy_import
from providers.audio import INPUT_RATE_HZ
from providers.base import ProviderCapabilities


def _pcm16_to_wav_bytes(pcm: bytes, sample_rate: int = INPUT_RATE_HZ) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class WhisperSTTProvider:
    name = "whisper_stt"
    capabilities = ProviderCapabilities(audio_in_hz=INPUT_RATE_HZ)

    def __init__(self, model_size: str = "base", api_key: str | None = None, base_url: str | None = None) -> None:
        self.model_size = model_size
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._local_model: Any = None

    def is_available(self) -> bool:
        return bool(lazy_import("faster_whisper") is not None or self.api_key)

    def transcribe(self, pcm16_bytes: bytes, sample_rate: int = INPUT_RATE_HZ) -> tuple[bool, str]:
        if not pcm16_bytes:
            return False, "No audio captured."

        fw = lazy_import("faster_whisper")
        if fw is not None:
            try:
                if self._local_model is None:
                    self._local_model = fw.WhisperModel(self.model_size, device="cpu", compute_type="int8")
                wav_io = io.BytesIO(_pcm16_to_wav_bytes(pcm16_bytes, sample_rate))
                segments, _ = self._local_model.transcribe(wav_io, beam_size=1)
                text = " ".join(seg.text.strip() for seg in segments).strip()
                return (True, text) if text else (False, "No speech detected in audio.")
            except Exception as exc:
                return False, f"faster-whisper error: {exc}"

        if not self.api_key:
            return False, "No STT backend available (install faster-whisper or configure OPENAI_API_KEY)."

        wav_bytes = _pcm16_to_wav_bytes(pcm16_bytes, sample_rate)
        boundary = "----DexBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/audio/transcriptions",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = str(data.get("text", "")).strip()
            return (True, text) if text else (False, "Empty transcription returned.")
        except Exception as exc:
            return False, f"STT API error: {exc}"
