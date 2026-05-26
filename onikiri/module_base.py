from __future__ import annotations

import asyncio
import json
import platform
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence


@dataclass
class SupervisorContext:
    config: Dict[str, Any]
    engagement_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def engagement_dir(self) -> Path:
        return Path(self.config["engagement_data_dir"])

    @property
    def allow_live_operations(self) -> bool:
        return bool(self.config.get("allow_live_operations", False))

    @property
    def public_mode(self) -> bool:
        return bool(self.config.get("public_mode", True))


class BaseModule:
    name = "base"
    label = "BASE"
    default_action = "status"
    status_hint = "inactive"

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "default_action": self.default_action,
            "status": self.status_hint,
            "actions": self.actions(),
        }

    def actions(self) -> Iterable[str]:
        return ("status",)

    async def execute(self, action: str, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        handler = getattr(self, f"action_{action}", None)
        if handler is None:
            return {"status": "error", "error": f"unsupported action: {action}"}
        result = handler(params, context)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {"status": "inactive", "module": self.name, "actions": list(self.actions())}

    async def run_command(self, command: Sequence[str], timeout: int = 30) -> Dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return {
            "command": list(command),
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def tool_status(self, *commands: str) -> Dict[str, bool]:
        return {command: shutil.which(command) is not None for command in commands}

    def environment_summary(self) -> Dict[str, Any]:
        return {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "hostname": platform.node(),
        }

    def safe_manifest(self, name: str, params: Dict[str, Any], note: str) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "manifest": {
                "name": name,
                "params": params,
                "note": note,
            },
        }

    def write_json_artifact(self, context: SupervisorContext, filename: str, payload: Dict[str, Any]) -> str:
        context.engagement_dir.mkdir(parents=True, exist_ok=True)
        path = context.engagement_dir / filename
        path.write_text(json.dumps(payload, indent=2))
        return str(path)

    @staticmethod
    def list_interfaces() -> list[str]:
        return [name for _, name in socket.if_nameindex()]
