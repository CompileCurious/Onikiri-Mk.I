"""
Onikiri Mk.I — Engagement Loader Module
UI-facing wrapper around the supervisor's EngagementManager.
Provides create/load/save/list/wipe operations callable from the HMI.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .base_module import BaseModule, ModuleState

_ENGAGEMENT_DIR = Path("/data/engagements")


class EngagementLoaderModule(BaseModule):
    name = "engagement_loader"
    description = "Engagement profile management: create, load, save, wipe"
    commands = {
        "list":        "List available engagement profiles",
        "new":         "Create a new blank engagement profile",
        "load":        "Load an engagement profile by name",
        "save":        "Save the active profile",
        "update":      "Update a field in the active profile",
        "get_active":  "Return the currently active profile",
        "add_finding": "Append a finding to the active profile",
        "wipe":        "Wipe all engagement data (field-wipe)",
    }

    async def register(self) -> None:
        _ENGAGEMENT_DIR.mkdir(parents=True, exist_ok=True)
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "list":        self._list,
            "new":         self._new,
            "load":        self._load,
            "save":        self._save,
            "update":      self._update,
            "get_active":  self._get_active,
            "add_finding": self._add_finding,
            "wipe":        self._wipe,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _list(self, _params: dict) -> dict:
        profiles = []
        for p in sorted(_ENGAGEMENT_DIR.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                profiles.append({
                    "name": data.get("name", p.stem),
                    "created_at": data.get("created_at"),
                    "findings_count": len(data.get("findings", [])),
                })
            except (json.JSONDecodeError, OSError):
                pass
        return {"profiles": profiles}

    async def _new(self, params: dict) -> dict:
        self._require(params, "name")
        name = self._sanitise_name(params["name"])
        path = _ENGAGEMENT_DIR / f"{name}.json"
        if path.exists():
            return {"error": f"engagement '{name}' already exists"}

        profile = {
            "schema_version": 1,
            "name": name,
            "created_at": time.time(),
            "scope": {"networks": [], "hosts": [], "domains": []},
            "credentials": [],
            "active_modules": [],
            "notes": "",
            "findings": [],
        }
        path.write_text(json.dumps(profile, indent=2))
        return {"created": name, "path": str(path)}

    async def _load(self, params: dict) -> dict:
        self._require(params, "name")
        name = self._sanitise_name(params["name"])
        path = _ENGAGEMENT_DIR / f"{name}.json"
        if not path.exists():
            return {"error": f"profile not found: {name}"}
        profile = json.loads(path.read_text())
        # Store as active in module state for subsequent operations
        self._active_profile = profile
        self._active_path = path
        return {"loaded": name, "profile": profile}

    async def _save(self, _params: dict) -> dict:
        if not hasattr(self, "_active_profile"):
            return {"error": "no active engagement"}
        self._active_path.write_text(
            json.dumps(self._active_profile, indent=2)
        )
        return {"saved": self._active_profile["name"]}

    async def _update(self, params: dict) -> dict:
        self._require(params, "key", "value")
        if not hasattr(self, "_active_profile"):
            return {"error": "no active engagement"}
        key = params["key"]
        allowed_keys = {"notes", "scope", "active_modules"}
        if key not in allowed_keys:
            raise ValueError(f"key not updatable: {key!r}")
        self._active_profile[key] = params["value"]
        return {"updated": key}

    async def _get_active(self, _params: dict) -> dict:
        if not hasattr(self, "_active_profile"):
            return {"active": None}
        return {"active": self._active_profile}

    async def _add_finding(self, params: dict) -> dict:
        self._require(params, "title", "severity")
        if not hasattr(self, "_active_profile"):
            return {"error": "no active engagement"}
        finding = {
            "id": len(self._active_profile["findings"]) + 1,
            "title": str(params["title"])[:256],
            "severity": str(params["severity"]),
            "description": str(params.get("description", "")),
            "timestamp": time.time(),
        }
        self._active_profile["findings"].append(finding)
        await self._save({})
        return {"finding": finding}

    async def _wipe(self, _params: dict) -> dict:
        import shutil
        if _ENGAGEMENT_DIR.exists():
            shutil.rmtree(_ENGAGEMENT_DIR)
        _ENGAGEMENT_DIR.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "_active_profile"):
            del self._active_profile
        if hasattr(self, "_active_path"):
            del self._active_path
        return {"wiped": True, "timestamp": time.time()}

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_name(name: str) -> str:
        import re
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())
        if not clean or len(clean) > 64:
            raise ValueError(f"invalid engagement name: {name!r}")
        return clean
