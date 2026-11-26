"""Sandboxed Python code & AST scientific math evaluator plugin."""

from __future__ import annotations

import ast
import contextlib
import datetime
import io
import json
import math
import operator
from typing import Any

from core.outcome import ToolOutcome

TOOL = {
    "name": "code_helper",
    "description": "Run sandboxed Python expressions/snippets (`py`) or AST math (`calc`).",
    "commands": ["py", "calc"],
}

SAFE_OPS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

SAFE_MATH_FUNCS: dict[str, Any] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "exp": math.exp, "abs": abs, "round": round, "floor": math.floor,
    "ceil": math.ceil, "factorial": math.factorial, "gcd": math.gcd,
    "radians": math.radians, "degrees": math.degrees, "pow": pow,
}

SAFE_MATH_CONSTS: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval_math_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_math_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in SAFE_MATH_CONSTS:
        return SAFE_MATH_CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPS:
        left = _eval_math_node(node.left)
        right = _eval_math_node(node.right)
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError("Exponent exceeds safe tactical computation bounds.")
        return SAFE_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPS:
        return SAFE_OPS[type(node.op)](_eval_math_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SAFE_MATH_FUNCS:
        return SAFE_MATH_FUNCS[node.func.id](*[_eval_math_node(a) for a in node.args])
    raise ValueError("Unsupported operation in tactical calculator.")


def _run_safe_python(code: str) -> tuple[bool, str]:
    blocked = ("import ", "__", "open(", "exec(", "eval(", "compile(", "globals(", "locals(", "getattr(", "setattr(", "delattr(", "os.", "sys.", "subprocess", "pathlib", "shutil", "socket")
    lowered = code.lower()
    for tok in blocked:
        if tok in lowered:
            return False, f"Security restraint engaged: `{tok.strip()}` is restricted in sandboxed `py` mode."

    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
        "chr": chr, "dict": dict, "divmod": divmod, "enumerate": enumerate,
        "filter": filter, "float": float, "format": format, "hex": hex,
        "int": int, "len": len, "list": list, "map": map, "max": max,
        "min": min, "oct": oct, "ord": ord, "pow": pow, "print": print,
        "range": range, "reversed": reversed, "round": round, "set": set,
        "slice": slice, "sorted": sorted, "str": str, "sum": sum,
        "tuple": tuple, "type": type, "zip": zip,
    }
    env: dict[str, Any] = {"__builtins__": safe_builtins, "math": math, "json": json, "datetime": datetime}
    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            try:
                tree = ast.parse(code, mode="eval")
                res = eval(compile(tree, "<jarvis-py>", "eval"), env, env)
                printed = stdout_buf.getvalue().strip()
                out = f"{printed}\n{repr(res)}" if (printed and res is not None) else (repr(res) if res is not None else (printed or "None"))
                return True, out
            except SyntaxError:
                tree = ast.parse(code, mode="exec")
                exec(compile(tree, "<jarvis-py>", "exec"), env, env)
                return True, stdout_buf.getvalue().strip() or "Executed successfully (no stdout)."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def handler(cmd: str, arg: str, _ctx: dict[str, Any]) -> ToolOutcome:
    if cmd == "calc":
        if not arg:
            return ToolOutcome(status="failed", summary="Usage: calc <expression>")
        try:
            res = _eval_math_node(ast.parse(arg, mode="eval"))
            return ToolOutcome(status="done", summary=f"{arg} = {res}", lines=[f"{arg}  =  {res}"])
        except Exception as exc:
            return ToolOutcome(status="failed", summary=f"Calculation error: {exc}")

    if not arg:
        return ToolOutcome(status="failed", summary="Usage: py <python expression or code>")
    ok, out = _run_safe_python(arg)
    return ToolOutcome(status="done" if ok else "failed", summary=out, lines=out.splitlines())
