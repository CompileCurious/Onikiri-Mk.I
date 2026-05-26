"""
Onikiri Mk.I — IPC Server
JSON-over-Unix-socket RPC.

Protocol (newline-delimited JSON):
  Request:  {"id": "<uuid>", "cmd": "<command>", "args": {...}}
  Response: {"id": "<uuid>", "status": "ok"|"error", "result": {...}}
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from .supervisor import Supervisor

SOCKET_PATH = Path("/run/onikiri/supervisor.sock")
_Handler = Callable[[dict], Awaitable[dict]]


class IPCServer:
    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._server: asyncio.Server | None = None
        self._handlers: dict[str, _Handler] = {
            "list_modules":    self._h_list_modules,
            "module_status":   self._h_module_status,
            "execute":         self._h_execute,
            "job_status":      self._h_job_status,
            "list_jobs":       self._h_list_jobs,
            "cancel_job":      self._h_cancel_job,
            "load_engagement": self._h_load_engagement,
            "wipe_engagement": self._h_wipe_engagement,
            "system_status":   self._h_system_status,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(SOCKET_PATH)
        )
        # Restrict socket access to root only
        os.chmod(SOCKET_PATH, stat.S_IRUSR | stat.S_IWUSR)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

    # ── Connection handler ────────────────────────────────────────────────────

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    continue
                response = await self._dispatch(request)
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, request: dict) -> dict:
        req_id = request.get("id", "")
        cmd = request.get("cmd", "")
        args = request.get("args", {})

        handler = self._handlers.get(cmd)
        if handler is None:
            return {
                "id": req_id,
                "status": "error",
                "result": {"message": f"unknown command: {cmd}"},
            }

        try:
            result = await handler(args)
            return {"id": req_id, "status": "ok", "result": result}
        except Exception as exc:  # noqa: BLE001
            return {
                "id": req_id,
                "status": "error",
                "result": {"message": str(exc)},
            }

    # ── Command handlers ──────────────────────────────────────────────────────

    async def _h_list_modules(self, _args: dict) -> dict:
        return {"modules": self._supervisor.module_loader.list_modules()}

    async def _h_module_status(self, args: dict) -> dict:
        name = args["module"]
        return self._supervisor.module_loader.get_status(name)

    async def _h_execute(self, args: dict) -> dict:
        module = args["module"]
        command = args["command"]
        params = args.get("params", {})
        job_id = await self._supervisor.job_queue.submit(
            self._supervisor.module_loader, module, command, params
        )
        return {"job_id": job_id}

    async def _h_job_status(self, args: dict) -> dict:
        return self._supervisor.job_queue.get_status(args["job_id"])

    async def _h_list_jobs(self, _args: dict) -> dict:
        return {"jobs": self._supervisor.job_queue.list_jobs()}

    async def _h_cancel_job(self, args: dict) -> dict:
        await self._supervisor.job_queue.cancel(args["job_id"])
        return {"cancelled": args["job_id"]}

    async def _h_load_engagement(self, args: dict) -> dict:
        return await self._supervisor.engagement.load(args["profile"])

    async def _h_wipe_engagement(self, _args: dict) -> dict:
        return await self._supervisor.engagement.wipe()

    async def _h_system_status(self, _args: dict) -> dict:
        return self._supervisor.get_system_status()
