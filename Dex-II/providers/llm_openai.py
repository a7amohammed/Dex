"""OpenAI-compatible /v1/chat/completions adapter (Ollama, LM Studio, OpenAI, vLLM)."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from providers.base import LiveEvent, ProviderCapabilities


class OpenAICompatibleLLM:
    name = "openai_compatible"
    capabilities = ProviderCapabilities(streaming=False, tool_calling=True)

    def __init__(self, base_url: str | None = None, model: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> LiveEvent:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choice = data.get("choices", [{}])[0].get("message", {})
        if choice.get("tool_calls"):
            call = choice["tool_calls"][0]["function"]
            return LiveEvent(
                kind="tool_call",
                tool_name=call["name"],
                tool_args=json.loads(call.get("arguments", "{}")),
            )
        return LiveEvent(kind="text", text=choice.get("content", ""))
