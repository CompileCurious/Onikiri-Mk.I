"""
Onikiri Mk.I — Module Loader
Dynamically loads and manages pentesting modules from one or more directories.

Search order
────────────
Directories are searched in the order provided to __init__.  A module found in
a later directory (e.g. /userdata/modules) replaces any module with the same
name from an earlier directory (e.g. the system modules dir).  This lets users
install updated or custom versions of system modules without modifying the
read-only system image.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

from .logger import get_logger

log = get_logger("module_loader")


class ModuleLoader:
    def __init__(self, modules_dirs: list[Path] | Path) -> None:
        # Accept a single Path for backwards-compatibility.
        if isinstance(modules_dirs, Path):
            modules_dirs = [modules_dirs]
        self._dirs: list[Path] = modules_dirs
        self._registry: dict[str, Any] = {}  # name → module instance

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def load_all(self) -> None:
        """
        Import every *.py file from each modules directory in order.
        Each file must contain exactly one class that subclasses BaseModule.
        Modules in later directories override same-named modules from earlier
        ones (user modules win over system modules).
        """
        from modules.base_module import BaseModule  # noqa: PLC0415

        for directory in self._dirs:
            if not directory.exists():
                log.debug("Module directory not found, skipping: %s", directory)
                continue
            for path in sorted(directory.glob("*.py")):
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
                            if instance.name in self._registry:
                                log.info(
                                    "User module %s overrides system module (from %s)",
                                    instance.name, directory,
                                )
                            else:
                                log.info("Loaded module: %s (from %s)", instance.name, directory)
                            self._registry[instance.name] = instance
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
