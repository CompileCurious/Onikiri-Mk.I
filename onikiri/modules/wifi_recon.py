from __future__ import annotations

from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class WifiReconModule(BaseModule):
    name = "wifi_recon"
    label = "WIRELESS"
    default_action = "survey"

    def actions(self) -> tuple[str, ...]:
        return ("status", "survey", "monitor_capability")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "tools": self.tool_status("iw", "iwconfig", "airmon-ng"),
            "interfaces": self.list_interfaces(),
        }

    async def action_survey(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        interface = params.get("interface", "wlan0")
        if params.get("live") and context.allow_live_operations and self.tool_status("iw").get("iw"):
            result = await self.run_command(["iw", "dev", interface, "info"])
            result.update({"status": "completed", "module": self.name, "interface": interface})
            return result
        return {
            "status": "inactive",
            "module": self.name,
            "interface": interface,
            "available_tools": self.tool_status("iw", "iwlist", "airmon-ng"),
            "note": "Live radio operations are configuration-gated; the public profile defaults to passive planning.",
        }

    def action_monitor_capability(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "interfaces": self.list_interfaces(),
            "drivers": self.tool_status("iw", "airmon-ng"),
            "note": "Monitor/injection enablement belongs in board-specific integration overlays and approved operator profiles.",
        }
