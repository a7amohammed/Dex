"""Contracts for optional Engine / LLM / STT / TTS providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool = False
    tool_calling: bool = False
    vision: bool = False
    audio_in_hz: int = 16000
    audio_out_hz: int = 24000


@dataclass
class LiveEvent:
    kind: str  # "text" | "tool_call" | "audio" | "done" | "error"
    text: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> LiveEvent: ...
