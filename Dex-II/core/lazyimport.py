"""Lazy import helper so heavy optional dependencies are paid only when used."""

from __future__ import annotations

import importlib
import importlib.util
from types import ModuleType


def is_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def lazy_import(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None
