"""Plugin Template — Copy this file (without the leading underscore) to add a new skill.

Files starting with `_` are skipped by core/plugin_loader.py so shared drivers stay private.
"""

from typing import Any
from core.outcome import ToolOutcome

TOOL = {
    "name": "example_skill",
    "description": "Describe what this skill does.",
    "commands": ["example"],
}


def handler(cmd: str, arg: str, ctx: dict[str, Any]) -> ToolOutcome:
    return ToolOutcome(
        status="done",
        summary=f"Executed {cmd} with '{arg}'",
        lines=[f"Example plugin received `{cmd}` with arguments: {arg}"],
    )
