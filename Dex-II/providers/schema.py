"""Tool declaration translators: Mark LVII TOOL <-> Gemini <-> OpenAI <-> Anthropic."""

from __future__ import annotations

from typing import Any


def to_gemini_declaration(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool.get("parameters", {"type": "OBJECT", "properties": {}}),
    }


def to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    params = _lowercase_types(tool.get("parameters", {"type": "object", "properties": {}}))
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": params,
        },
    }


def to_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    params = _lowercase_types(tool.get("parameters", {"type": "object", "properties": {}}))
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": params,
    }


def _lowercase_types(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.lower()
            else:
                out[k] = _lowercase_types(v)
        return out
    if isinstance(node, list):
        return [_lowercase_types(x) for x in node]
    return node
