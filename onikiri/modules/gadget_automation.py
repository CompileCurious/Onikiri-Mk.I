from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.gadget_automation.configfs import GadgetConfigFS
from onikiri.gadget_automation.engine import WorkflowEngine
from onikiri.gadget_automation.schema import schema_manifest, validate_workflow
from onikiri.gadget_automation.store import WorkflowStore
from onikiri.module_base import BaseModule, SupervisorContext

_SD_MOUNT = Path("/mnt/sd")


class GadgetAutomationModule(BaseModule):
    name = "gadget_automation"
    label = "GADGET"
    default_action = "status"
    status_hint = "inactive"

    def __init__(self) -> None:
        self._store: Optional[WorkflowStore] = None
        self._configfs = GadgetConfigFS()
        self._engine: Optional[WorkflowEngine] = None
        self._exec_task: Optional[asyncio.Task[Any]] = None
        self._exec_log: List[str] = []
        self._active_workflow_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Action registry
    # ------------------------------------------------------------------

    def actions(self) -> tuple[str, ...]:
        return (
            "status",
            "manifest",
            "list_workflows",
            "get_workflow",
            "save_workflow",
            "delete_workflow",
            "replace_blocks",
            "validate",
            "run_workflow",
            "stop_workflow",
            "get_logs",
            "get_gadget_state",
            "gadget_teardown",
            "sd_list",
            "sd_preview",
            "sd_import",
            "sd_export",
            "boot_list",
            "boot_import",
            "payload_create",
            "payload_add_file",
            "payload_list",
            "payload_clear",
        )

    # ------------------------------------------------------------------
    # Store accessor
    # ------------------------------------------------------------------

    def _get_store(self, context: SupervisorContext) -> WorkflowStore:
        if self._store is None:
            path = Path(
                context.config.get(
                    "gadget_workflow_path",
                    "/userdata/gadget/workflows.json",
                )
            )
            self._store = WorkflowStore(path)
        return self._store

    def _sd_mount(self, context: SupervisorContext) -> Path:
        return Path(context.config.get("sd_mount", "/mnt/sd"))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        running = self._exec_task is not None and not self._exec_task.done()
        return {
            "status": "active" if running else "inactive",
            "module": self.name,
            "running": running,
            "active_workflow_id": self._active_workflow_id,
            "gadget_profile": self._configfs.current_profile,
            "actions": list(self.actions()),
        }

    async def action_manifest(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {"status": "ok", "schema": schema_manifest()}

    async def action_list_workflows(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        return {"status": "ok", "workflows": store.list()}

    async def action_get_workflow(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        wid = params.get("workflow_id", "")
        store = self._get_store(context)
        wf = store.get(wid)
        if wf is None:
            return {"status": "error", "error": "workflow not found"}
        return {"status": "ok", "workflow": wf}

    async def action_save_workflow(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        workflow = params.get("workflow")
        if not isinstance(workflow, dict):
            return {"status": "error", "error": "workflow must be a JSON object"}
        errors = validate_workflow(workflow)
        if errors:
            return {"status": "error", "error": "; ".join(errors)}
        store = self._get_store(context)
        saved = store.save(workflow)
        return {"status": "ok", "workflow": saved}

    async def action_delete_workflow(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        wid = params.get("workflow_id", "")
        store = self._get_store(context)
        ok = store.delete(wid)
        return {"status": "ok" if ok else "error", "error": None if ok else "not found"}

    async def action_replace_blocks(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        wid = params.get("workflow_id", "")
        blocks = params.get("blocks", [])
        store = self._get_store(context)
        wf = store.replace_blocks(wid, blocks)
        if wf is None:
            return {"status": "error", "error": "workflow not found"}
        return {"status": "ok", "workflow": wf}

    async def action_validate(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        workflow = params.get("workflow")
        if not isinstance(workflow, dict):
            return {"status": "error", "error": "workflow must be a JSON object"}
        errors = validate_workflow(workflow)
        return {
            "status": "ok" if not errors else "invalid",
            "valid": len(errors) == 0,
            "errors": errors,
        }

    async def action_run_workflow(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self._exec_task and not self._exec_task.done():
            return {"status": "error", "error": "a workflow is already running"}

        wid = params.get("workflow_id")
        inline = params.get("workflow")

        # Resolve workflow
        if inline:
            workflow = inline
        elif wid:
            store = self._get_store(context)
            workflow = store.get(wid)
            if workflow is None:
                return {"status": "error", "error": "workflow not found"}
        else:
            return {"status": "error", "error": "workflow_id or workflow required"}

        # Validate before running
        errors = validate_workflow(workflow)
        if errors:
            return {"status": "error", "error": "; ".join(errors)}

        # Detect OS hint if provided
        detected_os = params.get("detected_os", "")

        sd = self._sd_mount(context)
        self._engine = WorkflowEngine(
            workflow=workflow,
            sd_mount=sd,
            configfs=self._configfs,
        )
        if detected_os:
            self._engine.set_detected_os(detected_os)

        self._active_workflow_id = wid

        async def _run_and_capture() -> None:
            result = await self._engine.run()
            self._exec_log = self._engine.log
            self._active_workflow_id = None

        loop = asyncio.get_event_loop()
        self._exec_task = loop.create_task(_run_and_capture())
        return {"status": "queued", "workflow_id": wid, "name": workflow.get("name", "")}

    async def action_stop_workflow(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self._engine:
            self._engine.stop()
        if self._exec_task and not self._exec_task.done():
            self._exec_task.cancel()
            try:
                await self._exec_task
            except (asyncio.CancelledError, Exception):
                pass
        self._active_workflow_id = None
        return {"status": "ok"}

    async def action_get_logs(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        log: List[str] = []
        if self._engine:
            log = list(self._engine.log)
        elif self._exec_log:
            log = list(self._exec_log)
        return {"status": "ok", "log": log}

    async def action_get_gadget_state(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "ok",
            "current_profile": self._configfs.current_profile,
        }

    async def action_gadget_teardown(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        result = await self._configfs.teardown()
        return {"status": "ok", "result": result}

    # ------------------------------------------------------------------
    # SD card operations
    # ------------------------------------------------------------------

    async def action_sd_list(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        files = store.sd_list(self._sd_mount(context))
        return {"status": "ok", "files": files}

    async def action_sd_preview(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        filename = params.get("filename", "")
        if not filename:
            return {"status": "error", "error": "filename required"}
        store = self._get_store(context)
        return store.sd_preview(filename, self._sd_mount(context))

    async def action_sd_import(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        filename = params.get("filename", "")
        if not filename:
            return {"status": "error", "error": "filename required"}
        store = self._get_store(context)
        return store.sd_import(filename, self._sd_mount(context))

    async def action_sd_export(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        wid = params.get("workflow_id", "")
        filename = params.get("filename", "")
        if not wid or not filename:
            return {"status": "error", "error": "workflow_id and filename required"}
        store = self._get_store(context)
        return store.sd_export(wid, filename, self._sd_mount(context))

    async def action_boot_list(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        files = store.boot_list()
        return {"status": "ok", "files": files}

    async def action_boot_import(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        filename = params.get("filename", "")
        if not filename:
            return {"status": "error", "error": "filename required"}
        store = self._get_store(context)
        return store.boot_import(filename)

    # ------------------------------------------------------------------
    # Payload (mass storage) image management
    # ------------------------------------------------------------------

    async def action_payload_create(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        """Create (or wipe and recreate) the FAT32 payload.img."""
        size_mb = int(params.get("size_mb", 64))
        result = await self._configfs.create_payload_image(size_mb)
        return {"status": result}

    async def action_payload_add_file(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        """Add a file to the payload image from base64-encoded data."""
        filename = params.get("filename", "").strip()
        data_b64 = params.get("data_b64", "")
        if not filename:
            return {"status": "error", "error": "filename required"}
        if not data_b64:
            return {"status": "error", "error": "data_b64 required"}
        try:
            data = base64.b64decode(data_b64)
        except Exception as exc:
            return {"status": "error", "error": f"invalid base64: {exc}"}
        # Reject path traversal
        safe = Path(filename).name
        if not safe or safe != filename:
            return {"status": "error", "error": "filename must be a plain name, no path components"}
        result = await self._configfs.add_payload_file(safe, data)
        return {"status": result, "filename": safe, "bytes": len(data)}

    async def action_payload_list(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        """List files currently in the payload image."""
        files = await self._configfs.list_payload_files()
        return {"status": "ok", "files": files}

    async def action_payload_clear(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        """Wipe the payload image back to a blank FAT32 volume."""
        result = await self._configfs.clear_payload()
        return {"status": result}
