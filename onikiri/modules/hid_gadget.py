from __future__ import annotations

from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class HidGadgetModule(BaseModule):
    name = "hid_gadget"
    label = "PAYLOADS"
    default_action = "manifest"

    def actions(self) -> tuple[str, ...]:
        return ("status", "manifest")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "inactive",
            "module": self.name,
            "tools": self.tool_status("modprobe"),
            "gadgetfs": {"present": False},
        }

    def action_manifest(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        manifest = {
            "sequence_name": params.get("sequence_name", "default"),
            "keystrokes": params.get("keystrokes", []),
            "inter_key_delay_ms": int(params.get("inter_key_delay_ms", 40)),
        }
        artifact = self.write_json_artifact(context, "hid-manifest.json", manifest)
        return {
            "status": "inactive",
            "module": self.name,
            "artifact": artifact,
            "note": "A manifest was written for later offline packaging; the public profile does not transmit HID sequences directly.",
        }
