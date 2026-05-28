from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.rules.schema import validate_rule


class RuleStore:
    """Persistent, in-memory rule list backed by a JSON file."""

    VERSION = "1.0"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._rules: List[Dict[str, Any]] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._rules = data.get("rules", [])
            except (json.JSONDecodeError, OSError):
                self._rules = []
        self._loaded = True

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"version": self.VERSION, "rules": self._rules}, indent=2)
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def all(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return list(self._rules)

    def get(self, rule_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        return next((r for r in self._rules if r["id"] == rule_id), None)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_loaded()
        rule = dict(rule)
        if not rule.get("id"):
            rule["id"] = uuid.uuid4().hex[:12]
        rule.setdefault("enabled", True)
        rule.setdefault("priority", len(self._rules))
        errors = validate_rule(rule)
        if errors:
            raise ValueError(f"invalid rule: {'; '.join(errors)}")
        self._rules.append(rule)
        self._persist()
        return rule

    def remove(self, rule_id: str) -> bool:
        self._ensure_loaded()
        before = len(self._rules)
        self._rules = [r for r in self._rules if r["id"] != rule_id]
        if len(self._rules) < before:
            self._persist()
            return True
        return False

    def toggle(self, rule_id: str) -> Optional[bool]:
        self._ensure_loaded()
        for rule in self._rules:
            if rule["id"] == rule_id:
                rule["enabled"] = not rule.get("enabled", True)
                self._persist()
                return bool(rule["enabled"])
        return None

    def reorder(self, ordered_ids: List[str]) -> List[Dict[str, Any]]:
        """Reorder rules to match the provided list of IDs. Rules not in the list are dropped."""
        self._ensure_loaded()
        index = {r["id"]: r for r in self._rules}
        reordered = [index[rid] for rid in ordered_ids if rid in index]
        for i, rule in enumerate(reordered):
            rule["priority"] = i
        self._rules = reordered
        self._persist()
        return list(self._rules)

    def move_up(self, rule_id: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        ids = [r["id"] for r in self._rules]
        try:
            idx = ids.index(rule_id)
        except ValueError:
            return list(self._rules)
        if idx > 0:
            ids[idx - 1], ids[idx] = ids[idx], ids[idx - 1]
            return self.reorder(ids)
        return list(self._rules)

    def move_down(self, rule_id: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        ids = [r["id"] for r in self._rules]
        try:
            idx = ids.index(rule_id)
        except ValueError:
            return list(self._rules)
        if idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
            return self.reorder(ids)
        return list(self._rules)
