from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict


class IPCError(RuntimeError):
    """Raised for supervisor IPC failures."""


async def send_request(socket_path: str | Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        writer.write(json.dumps(payload).encode("utf-8") + b"\n")
        await writer.drain()
        response = await reader.readline()
        if not response:
            raise IPCError("empty response from supervisor")
        return json.loads(response.decode("utf-8"))
    finally:
        writer.close()
        await writer.wait_closed()


class IPCClient:
    def __init__(self, socket_path: str | Path) -> None:
        self.socket_path = str(socket_path)

    async def request(self, action: str, **payload: Any) -> Dict[str, Any]:
        message = {"action": action, **payload}
        return await send_request(self.socket_path, message)
