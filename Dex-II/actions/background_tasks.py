"""Background task management action (start, list, check, steer, cancel)."""

from __future__ import annotations

from typing import Any

from core.outcome import ToolOutcome
from core.tasks.agents import list_agents
from core.tasks.engine import cancel_task, get_tasks_summary, start_task, steer_task
from core.tasks.store import load_task

TOOL = {
    "name": "background_tasks",
    "description": "Start, list, check, steer, or cancel background agent tasks and view reports.",
    "commands": ["task", "tasks"],
}


def handler(_cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    parts = arg.split(maxsplit=1) if arg else []
    sub = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "agents":
        agents = list_agents()
        lines = ["AVAILABLE MARK LVII AGENTS", "------------------------------------------------------------------------"]
        for a in agents.values():
            lines.append(f"  {a['name']:<12} [{a['mode']}]  {a['description']}")
        return ToolOutcome(status="done", summary=f"{len(agents)} agents loaded.", lines=lines)

    if sub in ("start", "research"):
        if not rest:
            return ToolOutcome(status="failed", summary="Usage: task start <goal>  (or `task research <topic>`)")
        agent_name = "researcher" if sub == "research" else "general"
        task = start_task(rest, agent_name=agent_name)
        lines = [
            f"BACKGROUND TASK LAUNCHED  ·  {task['id']}",
            f"  Agent  : {task['agent']} ({task['mode']})",
            f"  Goal   : {task['goal']}",
            f"  Status : {task['status']}",
            f"  Report : Dex-II/{task['report_file']}",
        ]
        return ToolOutcome(status="started", summary=f"Task {task['id']} completed.", lines=lines, data={"task": task})

    if sub == "check":
        if not rest:
            return ToolOutcome(status="failed", summary="Usage: task check <TSK-XXXXXX>")
        task = load_task(rest.upper())
        if not task:
            return ToolOutcome(status="failed", summary=f"Task '{rest}' not found.")
        lines = [
            f"TASK {task['id']}  ·  {task['status'].upper()}",
            f"  Goal   : {task['goal']}",
            f"  Agent  : {task['agent']} ({task['mode']})",
            f"  Report : Dex-II/{task['report_file']}",
            "  Checkpoints:",
            *[f"    {c['step']}. [{c['status'].upper()}] {c['label']}" for c in task.get("checkpoints", [])],
        ]
        return ToolOutcome(status="done", summary=f"Task {task['id']} status: {task['status']}", lines=lines)

    if sub == "steer":
        sp = rest.split(maxsplit=1)
        if len(sp) < 2:
            return ToolOutcome(status="failed", summary="Usage: task steer <TSK-XXXXXX> <instruction>")
        task = steer_task(sp[0], sp[1])
        if not task:
            return ToolOutcome(status="failed", summary=f"Task '{sp[0]}' not found.")
        return ToolOutcome(
            status="done",
            summary=f"Steered {task['id']}",
            lines=[f"Applied steering directive to {task['id']}: \"{sp[1]}\""],
        )

    if sub == "cancel":
        if not rest:
            return ToolOutcome(status="failed", summary="Usage: task cancel <TSK-XXXXXX>")
        task = cancel_task(rest)
        if not task:
            return ToolOutcome(status="failed", summary=f"Task '{rest}' not found.")
        return ToolOutcome(status="done", summary=f"Cancelled {task['id']}", lines=[f"Task {task['id']} marked cancelled."])

    # Default: list
    tasks = get_tasks_summary()
    if not tasks:
        return ToolOutcome(
            status="done",
            summary="No background tasks yet.",
            lines=["No background tasks recorded. Start one with: task start <goal>  or  task research <topic>"],
        )
    lines = ["BACKGROUND TASKS", "------------------------------------------------------------------------"]
    for t in tasks[:12]:
        lines.append(f"  {t['id']}  [{t['status']:<9}]  ({t['agent']})  {t['goal']}")
    return ToolOutcome(status="done", summary=f"{len(tasks)} tasks listed.", lines=lines)
