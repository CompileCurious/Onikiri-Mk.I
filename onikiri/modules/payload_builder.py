from __future__ import annotations

from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class PayloadBuilderModule(BaseModule):
    name = "payload_builder"
    label = "PAYLOADS"
    default_action = "template"

    def actions(self) -> tuple[str, ...]:
        return ("status", "template")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {"status": "inactive", "module": self.name}

    def action_template(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        template = {
            "name": params.get("name", "payload-template"),
            "delivery": params.get("delivery", "operator-reviewed"),
            "artifacts": params.get("artifacts", ["script", "config"]),
            "note": "Public builds emit structured payload manifests only; operator-specific execution content belongs in private overlays.",
        }
        artifact = self.write_json_artifact(context, "payload-template.json", template)
        return {"status": "inactive", "module": self.name, "artifact": artifact, "template": template}
