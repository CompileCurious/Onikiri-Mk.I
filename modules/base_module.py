"""
Onikiri Mk.I — BaseModule
Abstract base class for all pentesting modules.

Contract:
  - Every module MUST implement: name, description, commands, execute()
  - register() is called once at load time.
  - execute() is always awaited (use asyncio.to_thread for blocking work).
  - describe() provides the UI and IPC with status/capability data.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class ModuleState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class BaseModule(ABC):
    # ── Subclasses must set these ──────────────────────────────────────────────
    name: str = ""
    description: str = ""
    # Map of command_name → short description
    commands: dict[str, str] = {}

    def __init__(self) -> None:
        self.state = ModuleState.IDLE
        self._error: str | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def register(self) -> None:
        """
        Called once when the module is loaded.
        Subclasses may override to perform one-time setup
        (e.g. check for required binaries, create tmp dirs).
        """

    # ── Core API ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def execute(self, command: str, params: dict) -> Any:
        """
        Execute a named command with the provided parameters.
        Must return a JSON-serialisable value.
        Raise ValueError for unknown commands or invalid params.
        """

    # ── Status ────────────────────────────────────────────────────────────────

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "state": self.state,
            "error": self._error,
            "commands": self.commands,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _run_subprocess(
        self,
        args: list[str],
        timeout: float = 60.0,
        stdin: bytes | None = None,
    ) -> dict:
        """
        Run an external process, capture stdout/stderr, return structured output.
        Never passes user-supplied args directly — callers must sanitise.
        """
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"returncode": -1, "stdout": "", "stderr": "timeout", "timedout": True}

        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "timedout": False,
        }

    @staticmethod
    def _require(params: dict, *keys: str) -> None:
        """Raise ValueError if any required key is absent from params."""
        missing = [k for k in keys if k not in params]
        if missing:
            raise ValueError(f"missing required params: {', '.join(missing)}")

    @staticmethod
    def _sanitise_iface(iface: str) -> str:
        """Validate a network interface name to prevent injection."""
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-.")
        clean = "".join(c for c in iface if c in allowed)
        if not clean or clean != iface:
            raise ValueError(f"invalid interface name: {iface!r}")
        return clean
