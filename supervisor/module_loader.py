"""
Onikiri Mk.I — Module Loader
Dynamically loads and manages pentesting modules from the modules/ directory.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

from .logger import get_logger

log = get_logger("module_loader")


class ModuleLoader:
    def __init__(self, modules_dir: Path) -> None:
        self._dir = modules_dir
        self._registry: dict[str, Any] = {}  # name → module instance

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def load_all(self) -> None:
        """
        Import every *.py file in modules_dir (except __init__ and base_module).
        Each file must contain exactly one class that subclasses BaseModule.
        """
        from modules.base_module import BaseModule  # noqa: PLC0415

        for path in sorted(self._dir.glob("*.py")):
            if path.stem in ("__init__", "base_module"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(path.stem, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]

                for _name, obj in inspect.getmembers(mod, inspect.isclass):
                    if (
                        issubclass(obj, BaseModule)
                        and obj is not BaseModule
                        and obj.__module__ == mod.__name__
                    ):
                        instance = obj()
                        await instance.register()
                        self._registry[instance.name] = instance
                        log.info("Loaded module: %s", instance.name)
                        break
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to load %s: %s", path.name, exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_module(self, name: str) -> Any | None:
        return self._registry.get(name)

    def list_modules(self) -> list[dict]:
        return [m.describe() for m in self._registry.values()]

    def get_status(self, name: str) -> dict:
        mod = self._registry.get(name)
        if mod is None:
            return {"error": f"module not found: {name}"}
        return mod.describe()
