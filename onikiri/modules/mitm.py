from __future__ import annotations

from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class MitmModule(BaseModule):
    name = "mitm"
    label = "MITM"
    default_action = "plan"

    def actions(self) -> tuple[str, ...]:
        return ("status", "plan")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "tools": self.tool_status("bettercap", "mitmproxy", "arpspoof"),
            "note": "The public build ships planning/orchestration only; live interception remains disabled by default.",
        }

    def action_plan(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return self.safe_manifest(
            "mitm-plan",
            {
                "targets": params.get("targets", []),
                "dns_spoof": bool(params.get("dns_spoof", False)),
                "http_proxy": bool(params.get("http_proxy", True)),
            },
            "Validated operator manifest for an authorized engagement. No live interception is performed by the public profile.",
        )
