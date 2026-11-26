"""Lazy on-demand provider registry for LLM, STT, TTS, and pipeline engines."""

from __future__ import annotations

import importlib
from typing import Any

REGISTRY: dict[str, tuple[str, str]] = {
    "openai": ("providers.llm_openai", "OpenAICompatibleLLM"),
    "whisper": ("providers.stt_whisper", "WhisperSTTProvider"),
    "tts_system": ("providers.tts_system", "SystemTTSProvider"),
    "tts_piper": ("providers.tts_piper", "PiperTTSProvider"),
    "tts_elevenlabs": ("providers.tts_elevenlabs", "ElevenLabsTTSProvider"),
    "openwakeword": ("providers.wakeword_oww", "OpenWakeWordProvider"),
    "pipeline": ("providers.engine_pipeline", "PipelineEngine"),
}


def list_available_providers() -> list[str]:
    return ["gemini", *REGISTRY.keys()]


def provider_availability_report() -> list[dict[str, Any]]:
    from core.lazyimport import is_available
    import shutil

    return [
        {"name": "gemini", "kind": "LLM / Live", "ready": True, "notes": "Default built-in engine"},
        {"name": "openai", "kind": "LLM", "ready": True, "notes": "Any /v1/chat/completions endpoint"},
        {
            "name": "whisper",
            "kind": "STT",
            "ready": is_available("faster_whisper"),
            "notes": "CPU faster-whisper or OpenAI /audio/transcriptions",
        },
        {
            "name": "openwakeword",
            "kind": "Wake Word",
            "ready": is_available("openwakeword") and is_available("numpy"),
            "notes": "Local 'hey dex' wake-word detection (ONNX/TFLite)",
        },
        {
            "name": "tts_system",
            "kind": "TTS",
            "ready": bool(shutil.which("espeak-ng") or shutil.which("spd-say") or shutil.which("say")),
            "notes": "Linux espeak-ng/spd-say, macOS say, Windows SAPI",
        },
        {
            "name": "tts_piper",
            "kind": "TTS",
            "ready": bool(shutil.which("piper")),
            "notes": "Local Piper neural ONNX voices",
        },
        {
            "name": "tts_elevenlabs",
            "kind": "TTS",
            "ready": True,
            "notes": "Requires ELEVENLABS_API_KEY",
        },
    ]


def load_provider(name: str, **kwargs: Any) -> Any:
    key = name.strip().lower()
    if key not in REGISTRY:
        raise KeyError(f"Unknown optional provider '{name}'. Built-in default is 'gemini'.")
    mod_path, cls_name = REGISTRY[key]
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls(**kwargs)
