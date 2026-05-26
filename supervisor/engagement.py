"""
Onikiri Mk.I — Engagement Manager
Loads, persists, and wipes engagement profiles.

An engagement profile is a JSON file stored in /data/engagements/<name>.json.
It stores target scope, network credentials, active modules, and notes.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .logger import get_logger

log = get_logger("engagement")

_SCHEMA_VERSION = 1


class EngagementManager:
    def __init__(self, base_dir: Path) -> None:
        self._dir = base_dir
        self.current_profile: dict | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def load(self, profile_name: str) -> dict:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{profile_name}.json"

        if not path.exists():
            # Create a blank profile
            profile = self._blank(profile_name)
            path.write_text(json.dumps(profile, indent=2))
        else:
            profile = json.loads(path.read_text())
            if profile.get("schema_version") != _SCHEMA_VERSION:
                profile = self._migrate(profile)

        self.current_profile = profile
        log.info("Loaded engagement: %s", profile_name)
        return {"profile": profile}

    async def save(self) -> dict:
        if self.current_profile is None:
            return {"error": "no engagement loaded"}
        profile = self.current_profile
        path = self._dir / f"{profile['name']}.json"
        path.write_text(json.dumps(profile, indent=2))
        return {"saved": profile["name"]}

    async def wipe(self) -> dict:
        """
        Clear all engagement data instantly.
        Removes the entire /data/engagements directory and resets state.
        This is the field-wipe function.
        """
        if self._dir.exists():
            shutil.rmtree(self._dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.current_profile = None
        log.warning("Engagement data wiped")
        return {"wiped": True, "timestamp": time.time()}

    def update_field(self, key: str, value: object) -> None:
        if self.current_profile is not None:
            self.current_profile[key] = value

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _blank(name: str) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "name": name,
            "created_at": time.time(),
            "scope": {"networks": [], "hosts": [], "domains": []},
            "credentials": [],
            "active_modules": [],
            "notes": "",
            "findings": [],
        }

    @staticmethod
    def _migrate(profile: dict) -> dict:
        # Future: handle schema upgrades here
        profile["schema_version"] = _SCHEMA_VERSION
        return profile
