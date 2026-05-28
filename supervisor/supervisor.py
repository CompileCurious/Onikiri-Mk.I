#!/usr/bin/env python3
"""
Onikiri Mk.I — Supervisor
Entry point. Starts IPC server, loads modules, launches UI, manages lifecycle.

Design choice: Python over Go.
  - Pentesting ecosystem (scapy, impacket, etc.) is Python-native.
  - Dynamic module loading via importlib avoids recompilation.
  - asyncio provides concurrent job execution without thread complexity.
  - JSON IPC is trivial in Python; no serialisation library needed.
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from .ipc_server import IPCServer
from .job_queue import JobQueue
from .module_loader import ModuleLoader
from .engagement import EngagementManager
from .logger import configure_logging, get_logger

ONIKIRI_HOME = Path(os.environ.get("ONIKIRI_HOME", "/usr/local/onikiri"))
PID_FILE = Path("/run/onikiri/supervisor.pid")
UI_SCRIPT = ONIKIRI_HOME / "ui" / "main.py"

# Persistent userdata paths — live on the ext4 p3 partition (/userdata).
# These directories survive a reflash of the system image.
USERDATA_DIR     = Path("/userdata")
HID_DIR          = USERDATA_DIR / "hid"
USER_MODULES_DIR = USERDATA_DIR / "modules"
CONFIG_DIR       = USERDATA_DIR / "config"
CAPTURES_DIR     = USERDATA_DIR / "captures"
LOGS_DIR         = USERDATA_DIR / "logs"

# System (read-only) module directory — shipped inside the SquashFS image.
SYSTEM_MODULES_DIR = ONIKIRI_HOME / "modules"


class Supervisor:
    """
    Central coordinator. Owns the module registry, job queue, engagement state,
    and IPC server. Spawns the UI as a child process.
    """

    def __init__(self) -> None:
        configure_logging(log_dir=LOGS_DIR)
        self.log = get_logger("supervisor")
        # Load system modules first, then user-installed modules from /userdata/modules.
        # User modules are loaded second so they can supplement or override system ones.
        self.module_loader = ModuleLoader([SYSTEM_MODULES_DIR, USER_MODULES_DIR])
        self.job_queue = JobQueue()
        # Engagement captures persist to /userdata/captures/engagements/
        self.engagement = EngagementManager(CAPTURES_DIR / "engagements")
        self.ipc = IPCServer(self)
        self._ui_process: subprocess.Popen | None = None
        self._running = False

    # ── Public API used by IPCServer ──────────────────────────────────────────

    def get_system_status(self) -> dict:
        return {
            "modules": self.module_loader.list_modules(),
            "jobs": self.job_queue.list_jobs(),
            "engagement": self.engagement.current_profile,
            "uptime": self._uptime(),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._write_pid()

        self.log.info("Loading modules (system: %s, user: %s)",
                      SYSTEM_MODULES_DIR, USER_MODULES_DIR)
        await self.module_loader.load_all()

        self.log.info("Starting job queue")
        await self.job_queue.start()

        self.log.info("Starting IPC server")
        await self.ipc.start()

        self.log.info("Launching UI")
        self._launch_ui()

        self.log.info("Supervisor ready")

    async def stop(self) -> None:
        self._running = False
        self.log.info("Shutting down")

        if self._ui_process and self._ui_process.poll() is None:
            self._ui_process.terminate()
            try:
                self._ui_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._ui_process.kill()

        await self.ipc.stop()
        await self.job_queue.stop()

        if PID_FILE.exists():
            PID_FILE.unlink()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write_pid(self) -> None:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def _launch_ui(self) -> None:
        env = {
            **os.environ,
            "ONIKIRI_HOME": str(ONIKIRI_HOME),
            "ONIKIRI_HID_DIR": str(HID_DIR),
            "ONIKIRI_CONFIG_DIR": str(CONFIG_DIR),
            "ONIKIRI_CAPTURES_DIR": str(CAPTURES_DIR),
            "ONIKIRI_LOGS_DIR": str(LOGS_DIR),
        }
        self._ui_process = subprocess.Popen(
            [sys.executable, str(UI_SCRIPT)],
            env=env,
            stdin=subprocess.DEVNULL,
        )
        self.log.info("UI process started (pid=%d)", self._ui_process.pid)

    @staticmethod
    def _uptime() -> float:
        try:
            return float(Path("/proc/uptime").read_text().split()[0])
        except OSError:
            return 0.0


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    supervisor = Supervisor()

    def _shutdown(sig: int, _frame) -> None:  # noqa: ANN001
        supervisor.log.info("Signal %d received — stopping", sig)
        loop.create_task(supervisor.stop())
        loop.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        loop.run_until_complete(supervisor.start())
        loop.run_forever()
    finally:
        loop.run_until_complete(supervisor.stop())
        loop.close()


if __name__ == "__main__":
    main()
