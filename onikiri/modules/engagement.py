from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class EngagementModule(BaseModule):
    name = "engagement"
    label = "ENGAGEMENT"
    default_action = "active_profile"

    def actions(self) -> tuple[str, ...]:
        return ("status", "load_profile", "active_profile")

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "active" if context.engagement_profiles else "inactive",
            "module": self.name,
            "loaded_profiles": sorted(context.engagement_profiles),
        }

    def action_load_profile(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        path = Path(params["path"])
        profile = json.loads(path.read_text())
        context.engagement_profiles[profile["name"]] = profile
        return {"status": "completed", "module": self.name, "profile": profile}

    def action_active_profile(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        active = next(iter(context.engagement_profiles.values()), None)
        return {"status": "active" if active else "inactive", "module": self.name, "profile": active}
