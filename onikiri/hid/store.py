from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.hid.schema import validate_block


class BlockStore:
    """Persistent, in-memory block sequence backed by a JSON file."""

    VERSION = "1.0"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._blocks: List[Dict[str, Any]] = []
        self._meta: Dict[str, Any] = {}
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
                self._blocks = data.get("blocks", [])
                self._meta = {k: v for k, v in data.items() if k not in ("blocks", "version")}
            except (json.JSONDecodeError, OSError):
                self._blocks = []
        self._loaded = True

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "name": self._meta.get("name", "default"),
            "device_profile": self._meta.get("device_profile", "generic_keyboard"),
            "blocks": self._blocks,
        }
        self._path.write_text(json.dumps(payload, indent=2))

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def set_meta(self, key: str, value: Any) -> None:
        self._ensure_loaded()
        self._meta[key] = value
        self._persist()

    def get_meta(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return dict(self._meta)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def all(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return list(self._blocks)

    def get(self, block_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        return next((b for b in self._blocks if b["id"] == block_id), None)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, block: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_loaded()
        block = dict(block)
        if not block.get("id"):
            block["id"] = uuid.uuid4().hex[:12]
        block.setdefault("enabled", True)
        block.setdefault("order", len(self._blocks))
        errors = validate_block(block)
        if errors:
            raise ValueError(f"invalid block: {'; '.join(errors)}")
        self._blocks.append(block)
        self._persist()
        return block

    def remove(self, block_id: str) -> bool:
        self._ensure_loaded()
        before = len(self._blocks)
        self._blocks = [b for b in self._blocks if b["id"] != block_id]
        if len(self._blocks) < before:
            self._persist()
            return True
        return False

    def toggle(self, block_id: str) -> Optional[bool]:
        self._ensure_loaded()
        for block in self._blocks:
            if block["id"] == block_id:
                block["enabled"] = not block.get("enabled", True)
                self._persist()
                return bool(block["enabled"])
        return None

    def reorder(self, ordered_ids: List[str]) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        index = {b["id"]: b for b in self._blocks}
        reordered = [index[bid] for bid in ordered_ids if bid in index]
        for i, block in enumerate(reordered):
            block["order"] = i
        self._blocks = reordered
        self._persist()
        return list(self._blocks)

    def move_up(self, block_id: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        ids = [b["id"] for b in self._blocks]
        try:
            idx = ids.index(block_id)
        except ValueError:
            return list(self._blocks)
        if idx > 0:
            ids[idx - 1], ids[idx] = ids[idx], ids[idx - 1]
            return self.reorder(ids)
        return list(self._blocks)

    def move_down(self, block_id: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        ids = [b["id"] for b in self._blocks]
        try:
            idx = ids.index(block_id)
        except ValueError:
            return list(self._blocks)
        if idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
            return self.reorder(ids)
        return list(self._blocks)

    def replace_all(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace the entire block list (used for payload import)."""
        self._ensure_loaded()
        validated = []
        for block in blocks:
            if not block.get("id"):
                block["id"] = uuid.uuid4().hex[:12]
            block.setdefault("enabled", True)
            validated.append(block)
        self._blocks = validated
        self._persist()
        return list(self._blocks)
