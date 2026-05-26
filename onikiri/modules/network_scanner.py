from __future__ import annotations

import ipaddress
from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class NetworkScannerModule(BaseModule):
    name = "network_scanner"
    label = "RECON"
    default_action = "inventory"

    def actions(self) -> tuple[str, ...]:
        return ("status", "inventory", "scan")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "tools": self.tool_status("nmap", "masscan", "ip"),
            "interfaces": self.list_interfaces(),
        }

    async def action_inventory(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self.tool_status("ip").get("ip"):
            result = await self.run_command(["ip", "-j", "address", "show"])
            result.update({"status": "completed", "module": self.name})
            return result
        return {"status": "inactive", "module": self.name, "interfaces": self.list_interfaces()}

    async def action_scan(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        target = params.get("target", "127.0.0.1")
        ipaddress.ip_network(target, strict=False)
        tool = params.get("tool", "nmap")
        if tool not in {"nmap", "masscan"}:
            return {"status": "error", "error": f"unsupported tool: {tool}"}
        if params.get("live") and context.allow_live_operations and self.tool_status(tool).get(tool):
            command = [tool, target]
            if tool == "nmap":
                command = ["nmap", "-Pn", "-T4", target]
            result = await self.run_command(command, timeout=60)
            result.update({"status": "completed", "module": self.name, "target": target})
            return result
        return {
            "status": "inactive",
            "module": self.name,
            "target": target,
            "tool": tool,
            "note": "Default behavior is dry-run planning; set allow_live_operations in a private deployment to execute approved scans.",
        }
