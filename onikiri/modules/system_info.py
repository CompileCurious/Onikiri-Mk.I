from __future__ import annotations

import os
import platform
import shutil
import socket
from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class SystemInfoModule(BaseModule):
    name = "system_info"
    label = "SYSTEM"
    default_action = "snapshot"

    def actions(self) -> tuple[str, ...]:
        return ("status", "snapshot", "diagnostics")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {"status": "active", "module": self.name, "environment": self.environment_summary()}

    def action_snapshot(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        disk = shutil.disk_usage("/")
        return {
            "status": "completed",
            "module": self.name,
            "environment": self.environment_summary(),
            "kernel": platform.release(),
            "machine": platform.machine(),
            "interfaces": [name for _, name in socket.if_nameindex()],
            "loadavg": os.getloadavg() if hasattr(os, "getloadavg") else None,
            "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        }

    def action_diagnostics(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "completed",
            "module": self.name,
            "hostname": socket.gethostname(),
            "socket_path": context.config["socket_path"],
            "overlay_paths": context.config["overlay_paths"],
            "engagement_dir": str(context.engagement_dir),
        }
