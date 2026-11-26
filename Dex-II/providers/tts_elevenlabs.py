"""ElevenLabs streaming TTS adapter using standard library HTTPS."""

from __future__ import annotations

import json
import os
import urllib.request

from providers.audio import play_pcm_audio
from providers.base import ProviderCapabilities


class ElevenLabsTTSProvider:
    name = "elevenlabs_tts"
    capabilities = ProviderCapabilities(streaming=True, audio_out_hz=24000)

    def __init__(self, voice_id: str = "JBFqnCBsd6RMkjVDRZzb", api_key: str | None = None) -> None:
        self.voice_id = voice_id
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def speak(self, text: str) -> tuple[bool, str]:
        if not self.api_key:
            return False, "ELEVENLABS_API_KEY is not configured."
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=pcm_24000"
        payload = {"text": text, "model_id": "eleven_multilingual_v2"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "xi-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                pcm = resp.read()
            return play_pcm_audio(pcm, sample_rate=24000)
        except Exception as exc:
            return False, f"ElevenLabs TTS error: {exc}"
