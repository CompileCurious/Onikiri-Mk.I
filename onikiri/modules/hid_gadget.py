from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.hid.engine import BlockEngine
from onikiri.hid.parser import parse_payload_file
from onikiri.hid.schema import (
    BLOCK_CATEGORIES,
    BLOCK_TYPES,
    USB_DEVICE_PROFILES,
    validate_block,
)
from onikiri.hid.store import BlockStore
from onikiri.module_base import BaseModule, SupervisorContext

_KBD_DEVICE = Path("/dev/hidg0")
_MOUSE_DEVICE = Path("/dev/hidg1")
_CONFIGFS_BASE = Path("/sys/kernel/config/usb_gadget")
_GADGET_NAME = "onikiri"


class HidGadgetModule(BaseModule):
    name = "hid_gadget"
    label = "HID"
    default_action = "status"
    status_hint = "inactive"

    def __init__(self) -> None:
        self._store: Optional[BlockStore] = None
        self._engine: Optional[BlockEngine] = None
        self._running = False
        self._exec_task: Optional[asyncio.Task[Any]] = None

    # ------------------------------------------------------------------
    # Module metadata
    # ------------------------------------------------------------------

    def actions(self) -> tuple[str, ...]:
        return (
            "status",
            "manifest",
            "list_blocks",
            "add_block",
            "remove_block",
            "toggle_block",
            "reorder_blocks",
            "move_block_up",
            "move_block_down",
            "replace_blocks",
            "list_devices",
            "set_device",
            "setup_gadget",
            "teardown_gadget",
            "start",
            "stop",
            "sd_list",
            "sd_preview",
            "sd_import",
            "sd_run_raw",
            "export",
        )

    # ------------------------------------------------------------------
    # Store accessor
    # ------------------------------------------------------------------

    def _get_store(self, context: SupervisorContext) -> BlockStore:
        if self._store is None:
            path = Path(
                context.config.get(
                    "hid_sequence_path", "/data/engagements/hid-sequence.json"
                )
            )
            self._store = BlockStore(path)
        return self._store

    def _payload_dir(self, context: SupervisorContext) -> Path:
        return Path(context.config.get("hid_payload_dir", "/mnt/sdcard/payloads"))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        meta = store.get_meta()
        return {
            "status": "active" if self._running else "inactive",
            "module": self.name,
            "running": self._running,
            "device_profile": meta.get("device_profile", "generic_keyboard"),
            "sequence_name": meta.get("name", "default"),
            "block_count": len(store.all()),
            "kbd_device": str(_KBD_DEVICE),
            "kbd_present": _KBD_DEVICE.exists(),
            "mouse_present": _MOUSE_DEVICE.exists(),
            "configfs_present": (_CONFIGFS_BASE / _GADGET_NAME).exists(),
            "tools": self.tool_status("modprobe"),
        }

    def action_manifest(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        artifact = self.write_json_artifact(
            context, "hid-manifest.json",
            {"blocks": store.all(), **store.get_meta()},
        )
        return {
            "status": "inactive",
            "module": self.name,
            "artifact": artifact,
            "note": "Manifest written for offline review.",
        }

    # ------------------------------------------------------------------
    # Block management
    # ------------------------------------------------------------------

    def action_list_blocks(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        return {
            "status": "ok",
            "module": self.name,
            "blocks": store.all(),
            "meta": store.get_meta(),
            "schema": {
                "block_types": BLOCK_TYPES,
                "categories": BLOCK_CATEGORIES,
            },
        }

    def action_add_block(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        block_data = params.get("block", params)
        try:
            added = store.add(block_data)
            return {"status": "ok", "module": self.name, "block": added, "blocks": store.all()}
        except ValueError as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}

    def action_remove_block(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        block_id = params.get("block_id", params.get("id", ""))
        removed = store.remove(block_id)
        return {
            "status": "ok" if removed else "not_found",
            "module": self.name,
            "block_id": block_id,
            "blocks": store.all(),
        }

    def action_toggle_block(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        block_id = params.get("block_id", params.get("id", ""))
        new_state = store.toggle(block_id)
        if new_state is None:
            return {"status": "not_found", "module": self.name, "block_id": block_id}
        return {
            "status": "ok",
            "module": self.name,
            "block_id": block_id,
            "enabled": new_state,
            "blocks": store.all(),
        }

    def action_reorder_blocks(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        ordered_ids: List[str] = params.get("ordered_ids", params.get("ids", []))
        blocks = store.reorder(ordered_ids)
        return {"status": "ok", "module": self.name, "blocks": blocks}

    def action_move_block_up(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        block_id = params.get("block_id", params.get("id", ""))
        blocks = store.move_up(block_id)
        return {"status": "ok", "module": self.name, "blocks": blocks}

    def action_move_block_down(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        block_id = params.get("block_id", params.get("id", ""))
        blocks = store.move_down(block_id)
        return {"status": "ok", "module": self.name, "blocks": blocks}

    def action_replace_blocks(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        blocks_data: List[Dict[str, Any]] = params.get("blocks", [])
        blocks = store.replace_all(blocks_data)
        return {"status": "ok", "module": self.name, "blocks": blocks}

    # ------------------------------------------------------------------
    # Device profile management
    # ------------------------------------------------------------------

    def action_list_devices(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        return {
            "status": "ok",
            "module": self.name,
            "devices": {k: v for k, v in USB_DEVICE_PROFILES.items()},
        }

    def action_set_device(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        profile_id = params.get("profile_id", "generic_keyboard")
        if profile_id not in USB_DEVICE_PROFILES and not params.get("custom"):
            return {"status": "error", "module": self.name, "error": f"unknown profile: {profile_id!r}"}
        store.set_meta("device_profile", profile_id)
        if params.get("custom"):
            # Store custom VID/PID in meta
            store.set_meta("custom_device", {
                "vid": params.get("vid", "0x1d6b"),
                "pid": params.get("pid", "0x0104"),
                "manufacturer": params.get("manufacturer", "Custom"),
                "product": params.get("product", "USB Keyboard"),
            })
        return {"status": "ok", "module": self.name, "device_profile": profile_id}

    # ------------------------------------------------------------------
    # USB gadget ConfigFS setup / teardown
    # ------------------------------------------------------------------

    async def action_setup_gadget(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if not context.allow_live_operations:
            return self.safe_manifest(
                "setup-gadget",
                params,
                "USB gadget setup requires allow_live_operations=true.",
            )

        configfs = Path("/sys/kernel/config")
        if not configfs.exists():
            return {"status": "error", "module": self.name, "error": "configfs not mounted"}

        store = self._get_store(context)
        meta = store.get_meta()
        profile_id = meta.get("device_profile", "generic_keyboard")

        if profile_id in USB_DEVICE_PROFILES:
            profile = USB_DEVICE_PROFILES[profile_id]
        else:
            profile = meta.get("custom_device", USB_DEVICE_PROFILES["generic_keyboard"])

        gadget = _CONFIGFS_BASE / _GADGET_NAME
        enable_mouse = params.get("mouse", False)

        cmds: List[List[str]] = [
            ["mkdir", "-p", str(gadget)],
            ["sh", "-c", f"echo {profile['vid']} > {gadget}/idVendor"],
            ["sh", "-c", f"echo {profile['pid']} > {gadget}/idProduct"],
            ["mkdir", "-p", str(gadget / "strings/0x409")],
            ["sh", "-c", f"echo '{profile['manufacturer']}' > {gadget}/strings/0x409/manufacturer"],
            ["sh", "-c", f"echo '{profile['product']}' > {gadget}/strings/0x409/product"],
            ["sh", "-c", f"echo '{profile['serial']}' > {gadget}/strings/0x409/serialnumber"],
            ["mkdir", "-p", str(gadget / "configs/c.1/strings/0x409")],
            ["sh", "-c", f"echo 'Config 1' > {gadget}/configs/c.1/strings/0x409/configuration"],
            # Keyboard HID function
            ["mkdir", "-p", str(gadget / "functions/hid.0")],
            ["sh", "-c", f"echo 1 > {gadget}/functions/hid.0/protocol"],
            ["sh", "-c", f"echo 1 > {gadget}/functions/hid.0/subclass"],
            ["sh", "-c", f"echo 8 > {gadget}/functions/hid.0/report_length"],
            ["sh", "-c", f"ln -sf {gadget}/functions/hid.0 {gadget}/configs/c.1/ 2>/dev/null || true"],
        ]
        if enable_mouse:
            cmds += [
                ["mkdir", "-p", str(gadget / "functions/hid.1")],
                ["sh", "-c", f"echo 2 > {gadget}/functions/hid.1/protocol"],
                ["sh", "-c", f"echo 1 > {gadget}/functions/hid.1/subclass"],
                ["sh", "-c", f"echo 4 > {gadget}/functions/hid.1/report_length"],
                ["sh", "-c", f"ln -sf {gadget}/functions/hid.1 {gadget}/configs/c.1/ 2>/dev/null || true"],
            ]
        cmds.append(["sh", "-c",
                     f"ls /sys/class/udc/ | head -1 | xargs -I{{}} sh -c 'echo {{}} > {gadget}/UDC'"])

        errors: List[str] = []
        for cmd in cmds:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, err = await asyncio.wait_for(proc.communicate(), timeout=10)
                if proc.returncode not in (0, 1):
                    errors.append(f"{' '.join(cmd[:3])}: {err.decode().strip()[:80]}")
            except Exception as exc:
                errors.append(f"cmd error: {exc}")

        return {
            "status": "ok" if not errors else "partial",
            "module": self.name,
            "profile": profile_id,
            "mouse_enabled": enable_mouse,
            "kbd_device": str(_KBD_DEVICE),
            "errors": errors,
        }

    async def action_teardown_gadget(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if not context.allow_live_operations:
            return self.safe_manifest("teardown-gadget", {}, "Requires allow_live_operations=true.")

        gadget = _CONFIGFS_BASE / _GADGET_NAME
        script = (
            f"echo '' > {gadget}/UDC 2>/dev/null; "
            f"rm -f {gadget}/configs/c.1/hid.0 {gadget}/configs/c.1/hid.1; "
            f"rmdir {gadget}/configs/c.1/strings/0x409 2>/dev/null; "
            f"rmdir {gadget}/configs/c.1 2>/dev/null; "
            f"rmdir {gadget}/functions/hid.0 {gadget}/functions/hid.1 2>/dev/null; "
            f"rmdir {gadget}/strings/0x409 2>/dev/null; "
            f"rmdir {gadget} 2>/dev/null || true"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "sh", "-c", script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=10)
            return {"status": "ok", "module": self.name}
        except Exception as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def action_start(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self._running:
            return {"status": "already_running", "module": self.name}

        if not context.allow_live_operations:
            store = self._get_store(context)
            return self.safe_manifest(
                "hid-run",
                {"blocks": store.all()},
                "HID execution requires allow_live_operations=true.",
            )

        store = self._get_store(context)
        blocks = store.all()
        if not blocks:
            return {"status": "error", "module": self.name, "error": "no blocks defined"}

        engine = BlockEngine(
            blocks,
            kbd_device=_KBD_DEVICE,
            mouse_device=_MOUSE_DEVICE,
        )
        self._engine = engine
        self._running = True

        async def _run_and_cleanup() -> None:
            try:
                await engine.run()
            finally:
                self._running = False
                self._engine = None

        self._exec_task = asyncio.ensure_future(_run_and_cleanup())
        return {
            "status": "active",
            "module": self.name,
            "block_count": len(blocks),
        }

    async def action_stop(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self._engine is not None:
            self._engine.stop()
        if self._exec_task and not self._exec_task.done():
            self._exec_task.cancel()
            try:
                await asyncio.wait_for(self._exec_task, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._running = False
        self._engine = None
        self._exec_task = None
        return {"status": "inactive", "module": self.name}

    # ------------------------------------------------------------------
    # SD card file browser
    # ------------------------------------------------------------------

    def action_sd_list(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        payload_dir = self._payload_dir(context)
        if not payload_dir.exists():
            return {
                "status": "ok",
                "module": self.name,
                "files": [],
                "path": str(payload_dir),
                "note": "Payload directory not found.",
            }
        files = []
        for entry in sorted(payload_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in (".txt", ".duck", ".ducky", ".payload"):
                files.append({
                    "name": entry.name,
                    "size": entry.stat().st_size,
                    "ext": entry.suffix.lower(),
                })
        return {"status": "ok", "module": self.name, "files": files, "path": str(payload_dir)}

    def action_sd_preview(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        filename = params.get("filename", "")
        if not filename or "/" in filename or ".." in filename:
            return {"status": "error", "module": self.name, "error": "invalid filename"}
        path = self._payload_dir(context) / filename
        if not path.exists():
            return {"status": "error", "module": self.name, "error": "file not found"}
        try:
            content = path.read_text(errors="replace")
            # Limit preview to first 4KB
            preview = content[:4096]
            return {
                "status": "ok",
                "module": self.name,
                "filename": filename,
                "preview": preview,
                "truncated": len(content) > 4096,
            }
        except OSError as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}

    def action_sd_import(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        filename = params.get("filename", "")
        if not filename or "/" in filename or ".." in filename:
            return {"status": "error", "module": self.name, "error": "invalid filename"}
        path = self._payload_dir(context) / filename
        if not path.exists():
            return {"status": "error", "module": self.name, "error": "file not found"}
        try:
            content = path.read_text(errors="replace")
            fmt, blocks = parse_payload_file(filename, content)
            store = self._get_store(context)
            imported = store.replace_all(blocks)
            store.set_meta("name", filename)
            return {
                "status": "ok",
                "module": self.name,
                "filename": filename,
                "format": fmt,
                "block_count": len(imported),
                "blocks": imported,
            }
        except Exception as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}

    async def action_sd_run_raw(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        """Parse and immediately execute a payload file from the SD card."""
        import_result = self.action_sd_import(params, context)
        if import_result["status"] == "error":
            return import_result
        return await self.action_start({}, context)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def action_export(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        filename = params.get("filename", "hid-sequence.json")
        if "/" in filename or ".." in filename:
            return {"status": "error", "module": self.name, "error": "invalid filename"}
        export_path = self._payload_dir(context) / filename
        export_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import json
            payload = {
                "version": "1.0",
                **store.get_meta(),
                "blocks": store.all(),
            }
            export_path.write_text(json.dumps(payload, indent=2))
            return {"status": "ok", "module": self.name, "path": str(export_path)}
        except OSError as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}
