from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.gadget_automation.schema import validate_workflow, SCHEMA_VERSION

_SD_MOUNT = Path("/mnt/sd")
_WORKFLOW_EXTENSIONS = {".json", ".workflow", ".blocks"}


class WorkflowStore:
    """
    Persistent, in-memory workflow store backed by a JSON file.
    Multiple named workflows are stored in a single catalogue file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._workflows: Dict[str, Dict[str, Any]] = {}
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
                self._workflows = data.get("workflows", {})
            except (json.JSONDecodeError, OSError):
                self._workflows = {}
        self._loaded = True

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "workflows": self._workflows,
        }, indent=2))

    # ------------------------------------------------------------------
    # Workflow CRUD
    # ------------------------------------------------------------------

    def list(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return [
            {
                "id": wid,
                "name": w.get("name", wid),
                "trigger": w.get("trigger", {}).get("type", "manual"),
                "block_count": len(w.get("blocks", [])),
            }
            for wid, w in self._workflows.items()
        ]

    def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        return self._workflows.get(workflow_id)

    def save(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_loaded()
        wid = workflow.get("id") or uuid.uuid4().hex[:12]
        workflow["id"] = wid
        workflow.setdefault("version", SCHEMA_VERSION)
        workflow.setdefault("name", f"workflow_{wid}")
        workflow.setdefault("trigger", {"type": "manual", "params": {}})
        workflow.setdefault("blocks", [])
        # Assign IDs to blocks that lack them
        for block in workflow["blocks"]:
            if not block.get("id"):
                block["id"] = uuid.uuid4().hex[:12]
            block.setdefault("enabled", True)
        self._workflows[wid] = workflow
        self._persist()
        return workflow

    def delete(self, workflow_id: str) -> bool:
        self._ensure_loaded()
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            self._persist()
            return True
        return False

    def replace_blocks(self, workflow_id: str, blocks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return None
        for block in blocks:
            if not block.get("id"):
                block["id"] = uuid.uuid4().hex[:12]
            block.setdefault("enabled", True)
        wf["blocks"] = blocks
        self._persist()
        return wf

    # ------------------------------------------------------------------
    # SD card operations
    # ------------------------------------------------------------------

    def sd_list(self, sd_mount: Path = _SD_MOUNT) -> List[Dict[str, Any]]:
        """List workflow files on the SD card."""
        if not sd_mount.exists():
            return []
        result = []
        for p in sorted(sd_mount.iterdir()):
            if p.is_file() and p.suffix.lower() in _WORKFLOW_EXTENSIONS:
                result.append({
                    "name": p.name,
                    "size": p.stat().st_size,
                    "extension": p.suffix.lower(),
                })
        return result

    def sd_preview(self, filename: str, sd_mount: Path = _SD_MOUNT, max_bytes: int = 4096) -> Dict[str, Any]:
        """Return a preview of a workflow file from SD card."""
        path = sd_mount / filename
        if not path.exists() or not path.is_file():
            return {"status": "error", "error": "file not found"}
        raw = path.read_bytes()
        truncated = len(raw) > max_bytes
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        # Try to parse as JSON
        structure: Optional[Dict[str, Any]] = None
        try:
            structure = json.loads(raw.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError):
            pass
        return {
            "status": "ok",
            "preview": text,
            "truncated": truncated,
            "parseable": structure is not None,
            "block_count": len(structure.get("blocks", [])) if structure else 0,
        }

    def sd_import(self, filename: str, sd_mount: Path = _SD_MOUNT) -> Dict[str, Any]:
        """Import and validate a workflow from SD card, saving to store."""
        path = sd_mount / filename
        if not path.exists() or not path.is_file():
            return {"status": "error", "error": "file not found"}
        try:
            data = json.loads(path.read_text(errors="replace"))
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": f"JSON parse error: {exc}"}
        errors = validate_workflow(data)
        if errors:
            return {"status": "error", "error": "; ".join(errors)}
        data["name"] = data.get("name") or path.stem
        workflow = self.save(data)
        return {"status": "ok", "workflow": workflow}

    def sd_export(self, workflow_id: str, filename: str, sd_mount: Path = _SD_MOUNT) -> Dict[str, Any]:
        """Export a workflow to SD card."""
        wf = self.get(workflow_id)
        if wf is None:
            return {"status": "error", "error": "workflow not found"}
        if not sd_mount.exists():
            return {"status": "error", "error": "SD card not mounted"}
        path = sd_mount / filename
        path.write_text(json.dumps(wf, indent=2))
        return {"status": "ok", "path": str(path)}

    def boot_list(self, boot_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        """List workflow files in /boot or the boot partition."""
        if boot_dir is None:
            boot_dir = Path("/boot/onikiri/workflows")
        if not boot_dir.exists():
            return []
        result = []
        for p in sorted(boot_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in _WORKFLOW_EXTENSIONS:
                result.append({"name": p.name, "size": p.stat().st_size})
        return result

    def boot_import(self, filename: str, boot_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Import a workflow from the boot partition."""
        if boot_dir is None:
            boot_dir = Path("/boot/onikiri/workflows")
        path = boot_dir / filename
        if not path.exists():
            return {"status": "error", "error": "boot file not found"}
        try:
            data = json.loads(path.read_text(errors="replace"))
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": f"JSON parse error: {exc}"}
        errors = validate_workflow(data)
        if errors:
            return {"status": "error", "error": "; ".join(errors)}
        data["name"] = data.get("name") or path.stem
        workflow = self.save(data)
        return {"status": "ok", "workflow": workflow}
