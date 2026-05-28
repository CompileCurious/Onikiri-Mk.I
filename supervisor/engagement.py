"""
Onikiri Mk.I — Engagement Manager
Loads, persists, and wipes engagement profiles.

An engagement profile is a JSON file stored in /userdata/captures/engagements/<name>.json.
It stores target scope, network credentials, active modules, and notes.

No-RTC naming
─────────────
The device has no real-time clock so wall-clock timestamps cannot be used for
file naming.  Engagements are numbered with a monotonic counter stored at
/userdata/.seq_counter.  Counter values are never reused (the counter only ever
increments) so names like "eng-00003" are globally unique across reflashes as
long as /userdata is preserved.
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

    # ── No-RTC sequential counter ─────────────────────────────────────────────

    def _next_seq(self) -> int:
        """Increment and return a monotonic counter from /userdata/.seq_counter.

        Safe without an RTC: the counter file lives on the persistent /userdata
        partition so values survive reboots and reflashes (as long as p3 is kept).
        Counter starts at 1 and only ever increases.
        """
        counter_file = self._dir.parent / ".seq_counter"
        try:
            current = int(counter_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            current = 0
        next_val = current + 1
        counter_file.parent.mkdir(parents=True, exist_ok=True)
        counter_file.write_text(str(next_val))
        return next_val

    # ── Public API ────────────────────────────────────────────────────────────

    def list_profiles(self) -> dict:
        """Return all saved engagement names from /userdata/captures/engagements/."""
        self._dir.mkdir(parents=True, exist_ok=True)
        profiles = sorted(p.stem for p in self._dir.glob("*.json"))
        current_name = self.current_profile["name"] if self.current_profile else None
        return {"profiles": profiles, "current": current_name}

    async def new(self, name: str | None = None) -> dict:
        """Create a new blank engagement, auto-naming it if no name is given.

        Auto-generated names use the sequential counter: ``eng-00001``,
        ``eng-00002``, etc.  These are unique without a wall-clock RTC.
        """
        if name is None:
            name = f"eng-{self._next_seq():05d}"
        return await self.load(name)

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
        Removes the entire /userdata/captures/engagements directory and resets state.
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
