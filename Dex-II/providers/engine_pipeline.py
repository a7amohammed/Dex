"""Pipeline engine: STT -> LLM -> TTS wearing the LiveEvent session interface."""

from __future__ import annotations

from typing import Any, Callable

from providers.base import LiveEvent, ProviderCapabilities


class PipelineEngine:
    name = "engine_pipeline"
    capabilities = ProviderCapabilities(streaming=False, tool_calling=True)

    def __init__(self, stt: Any, llm_fn: Callable[[str], str], tts: Any = None) -> None:
        self.stt = stt
        self.llm_fn = llm_fn
        self.tts = tts

    def process_audio(self, pcm16_bytes: bytes) -> list[LiveEvent]:
        events: list[LiveEvent] = []
        if self.stt is None or not self.stt.is_available():
            events.append(LiveEvent(kind="error", text="STT provider unavailable."))
            return events

        ok, transcript = self.stt.transcribe(pcm16_bytes)
        if not ok:
            events.append(LiveEvent(kind="error", text=transcript))
            return events

        events.append(LiveEvent(kind="text", text=f"USER: {transcript}"))
        reply = self.llm_fn(transcript)
        events.append(LiveEvent(kind="text", text=reply))

        if self.tts is not None and self.tts.is_available():
            spoken_ok, msg = self.tts.speak(reply)
            if not spoken_ok:
                events.append(LiveEvent(kind="error", text=msg))
            else:
                events.append(LiveEvent(kind="audio", text=msg))

        events.append(LiveEvent(kind="done"))
        return events
