from __future__ import annotations

from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class BluetoothReconModule(BaseModule):
    name = "bluetooth_recon"
    label = "WIRELESS"
    default_action = "survey"

    def actions(self) -> tuple[str, ...]:
        return ("status", "survey")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "tools": self.tool_status("btmgmt", "bluetoothctl"),
        }

    async def action_survey(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self.tool_status("btmgmt").get("btmgmt") and params.get("live") and context.allow_live_operations:
            result = await self.run_command(["btmgmt", "info"])
            result.update({"status": "completed", "module": self.name})
            return result
        return {
            "status": "inactive",
            "module": self.name,
            "note": "Bluetooth discovery is available once an approved private profile enables live operations.",
            "tools": self.tool_status("btmgmt", "bluetoothctl"),
        }
