"""Core structured outcome definitions for Mark LVII tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OutcomeStatus = Literal["done", "unverified", "failed", "ask", "started"]


@dataclass
class ToolOutcome:
    status: OutcomeStatus
    summary: str
    lines: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    confirm_token: str | None = None
    untrusted_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "summary": self.summary,
            "lines": self.lines or [self.summary],
            "data": self.data,
        }
        if self.confirm_token:
            payload["confirm_token"] = self.confirm_token
        if self.untrusted_source:
            payload["untrusted_source"] = self.untrusted_source
        return payload


def wrap_untrusted(source: str, content: str) -> str:
    """Wrap external or file-sourced text so the model treats it strictly as data."""
    return f"[UNTRUSTED_DATA source={source}]\n{content}\n[/UNTRUSTED_DATA]"
