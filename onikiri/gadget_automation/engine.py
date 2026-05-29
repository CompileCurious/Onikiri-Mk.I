from __future__ import annotations

import asyncio
import json
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.gadget_automation.configfs import GadgetConfigFS
from onikiri.hid.engine import _type_text, _key_tap, _resolve_key, _resolve_modifiers
from onikiri.hid.schema import char_to_hid

_KBD_DEVICE = Path("/dev/hidg0")
_MOUSE_DEVICE = Path("/dev/hidg1")
_SERIAL_DEVICE = Path("/dev/ttyGS0")
_SD_MOUNT = Path("/mnt/sd")


# ---------------------------------------------------------------------------
# Low-level serial helpers
# ---------------------------------------------------------------------------

async def _serial_write(text: str, device: Path) -> None:
    if not device.exists():
        return
    await asyncio.to_thread(_serial_write_sync, text.encode("utf-8"), device)


def _serial_write_sync(data: bytes, device: Path) -> None:
    with device.open("wb") as dev:
        dev.write(data)


async def _serial_read_until(match: str, timeout_s: float, device: Path) -> bool:
    """Read from serial until match string is found or timeout expires."""
    if not device.exists():
        return False
    deadline = asyncio.get_event_loop().time() + timeout_s
    buf = b""
    enc = match.encode("utf-8")
    try:
        while asyncio.get_event_loop().time() < deadline:
            chunk = await asyncio.to_thread(_serial_read_chunk, device)
            if chunk:
                buf += chunk
                if enc in buf:
                    return True
            else:
                await asyncio.sleep(0.05)
    except Exception:
        pass
    return False


def _serial_read_chunk(device: Path) -> bytes:
    try:
        with device.open("rb") as dev:
            return dev.read(256)
    except OSError:
        return b""


# ---------------------------------------------------------------------------
# Mouse report helper
# ---------------------------------------------------------------------------

def _send_mouse_report_sync(buttons: int, x: int, y: int, scroll: int, device: Path) -> None:
    if not device.exists():
        return
    report = struct.pack("4b", buttons, max(-127, min(127, x)),
                         max(-127, min(127, y)), max(-127, min(127, scroll)))
    with device.open("wb") as dev:
        dev.write(report)


async def _mouse_report(buttons: int, x: int, y: int, scroll: int, device: Path) -> None:
    await asyncio.to_thread(_send_mouse_report_sync, buttons, x, y, scroll, device)


# ---------------------------------------------------------------------------
# Workflow Execution Engine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    """
    Deterministic sequential executor for gadget automation workflows.

    Workflow structure:
      {
        "version": "1.0",
        "name": "...",
        "trigger": {"type": "manual", "params": {}},
        "blocks": [ ... ]
      }

    Call `run()` to execute.  Call `stop()` to cancel.
    Check `is_running` for current state.
    """

    def __init__(
        self,
        workflow: Dict[str, Any],
        sd_mount: Path = _SD_MOUNT,
        kbd_device: Path = _KBD_DEVICE,
        mouse_device: Path = _MOUSE_DEVICE,
        serial_device: Path = _SERIAL_DEVICE,
        configfs: Optional[GadgetConfigFS] = None,
    ) -> None:
        self.workflow = workflow
        self.sd = sd_mount
        self.kbd = kbd_device
        self.mouse = mouse_device
        self.serial = serial_device
        self.configfs = configfs or GadgetConfigFS()
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop_event = asyncio.Event()
        self.log: List[str] = []
        # Detected OS from host (set by if_os probing or external trigger)
        self._detected_os: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()

    async def run(self) -> Dict[str, Any]:
        self._stop_event.clear()
        self.log = []
        blocks = [b for b in self.workflow.get("blocks", []) if b.get("enabled", True)]
        try:
            executed = await self._exec_blocks(blocks, 0, len(blocks))
            return {"status": "completed", "executed": executed, "log": self.log}
        except asyncio.CancelledError:
            return {"status": "stopped", "log": self.log}
        except Exception as exc:
            self.log.append(f"[ERROR] {exc}")
            return {"status": "error", "error": str(exc), "log": self.log}

    # ------------------------------------------------------------------
    # Block dispatcher
    # ------------------------------------------------------------------

    async def _exec_blocks(self, blocks: List[Dict[str, Any]], start: int, end: int) -> int:
        i = start
        executed = 0
        while i < end:
            if self._stop_event.is_set():
                break
            block = blocks[i]
            btype = block.get("type", "")
            params = block.get("params", {})
            self.log.append(f"[{i}] {btype}")

            if btype == "delay":
                ms = max(0, int(params.get("ms", 500)))
                await asyncio.sleep(ms / 1000.0)
                i += 1

            elif btype == "wait_event":
                ms = max(0, int(params.get("timeout_ms", 10000)))
                await asyncio.sleep(ms / 1000.0)
                i += 1

            elif btype == "stop_workflow":
                self._stop_event.set()
                break

            # ------------------------------------------------------------------
            # Flow: if_os / else_block / end_if
            # ------------------------------------------------------------------
            elif btype == "if_os":
                target_os = (params.get("os") or "").lower()
                condition_met = self._detected_os == target_os
                i += 1
                # Find matching else_block / end_if
                else_idx, end_if_idx = self._find_if_boundaries(blocks, i, end)
                if condition_met:
                    branch_end = else_idx if else_idx is not None else end_if_idx
                    if branch_end is None:
                        branch_end = end
                    await self._exec_blocks(blocks, i, branch_end)
                else:
                    if else_idx is not None:
                        branch_end = end_if_idx if end_if_idx is not None else end
                        await self._exec_blocks(blocks, else_idx + 1, branch_end)
                i = (end_if_idx + 1) if end_if_idx is not None else end

            elif btype in ("else_block", "end_if"):
                # Encountered when nested — skip
                i += 1

            # ------------------------------------------------------------------
            # Flow: loop_n / end_loop
            # ------------------------------------------------------------------
            elif btype == "loop_n":
                count = max(0, int(params.get("count", 1)))
                i += 1
                end_loop_idx = self._find_end_loop(blocks, i, end)
                loop_end = end_loop_idx if end_loop_idx is not None else end
                for _ in range(count):
                    if self._stop_event.is_set():
                        break
                    await self._exec_blocks(blocks, i, loop_end)
                i = (end_loop_idx + 1) if end_loop_idx is not None else end

            elif btype == "end_loop":
                i += 1

            # ------------------------------------------------------------------
            # HID
            # ------------------------------------------------------------------
            elif btype == "hid_type_text":
                text = params.get("text", "")
                delay_ms = max(1, int(params.get("delay_ms", 20)))
                await _type_text(text, delay_ms, self.kbd)
                i += 1

            elif btype == "hid_press_key":
                sc = _resolve_key(params.get("key", ""))
                await _key_tap(0, sc, self.kbd)
                i += 1

            elif btype == "hid_key_combo":
                raw_mods = params.get("modifiers", "")
                if isinstance(raw_mods, str):
                    mods = [m.strip() for m in raw_mods.split(",") if m.strip()]
                else:
                    mods = list(raw_mods)
                modifier = _resolve_modifiers(mods)
                sc = _resolve_key(params.get("key", ""))
                await _key_tap(modifier, sc, self.kbd)
                i += 1

            elif btype == "hid_mouse_move":
                x = int(params.get("x", 0))
                y = int(params.get("y", 0))
                await _mouse_report(0, x, y, 0, self.mouse)
                await asyncio.sleep(0.02)
                i += 1

            elif btype == "hid_mouse_click":
                btn_map = {"left": 0x01, "right": 0x02, "middle": 0x04}
                btn_val = btn_map.get(params.get("button", "left"), 0x01)
                count = max(1, int(params.get("count", 1)))
                for _ in range(count):
                    await _mouse_report(btn_val, 0, 0, 0, self.mouse)
                    await asyncio.sleep(0.05)
                    await _mouse_report(0, 0, 0, 0, self.mouse)
                    await asyncio.sleep(0.05)
                i += 1

            elif btype == "hid_scroll":
                amount = int(params.get("amount", 3))
                await _mouse_report(0, 0, 0, amount, self.mouse)
                await asyncio.sleep(0.02)
                await _mouse_report(0, 0, 0, 0, self.mouse)
                i += 1

            elif btype == "hid_paste_from_sd":
                filename = params.get("filename", "")
                path = self.sd / filename
                if path.exists() and path.is_file():
                    text = path.read_text(errors="replace")
                    await _type_text(text, 20, self.kbd)
                    self.log.append(f"  pasted {len(text)} chars from {filename}")
                else:
                    self.log.append(f"  SD file not found: {filename}")
                i += 1

            elif btype == "hid_upload_from_sd":
                # Simulate uploading: type a shell command that copies via USB channel
                filename = params.get("filename", "")
                destination = params.get("destination", "")
                cmd = f"cp /mnt/usb/{filename} {destination}\n"
                await _type_text(cmd, 20, self.kbd)
                i += 1

            elif btype == "hid_download_file":
                url = params.get("url", "")
                local_path = params.get("local_path", "")
                cmd = f"curl -o {local_path} {url}\n"
                await _type_text(cmd, 20, self.kbd)
                i += 1

            # ------------------------------------------------------------------
            # Serial
            # ------------------------------------------------------------------
            elif btype == "serial_send_string":
                text = params.get("text", "")
                device = Path(params.get("device", str(self.serial)))
                await _serial_write(text, device)
                i += 1

            elif btype == "serial_send_sequence":
                raw = params.get("sequence", "")
                device = Path(params.get("device", str(self.serial)))
                try:
                    if isinstance(raw, list):
                        seq = bytes(raw)
                    elif raw.strip().startswith("["):
                        seq = bytes(json.loads(raw))
                    else:
                        seq = bytes(int(h.strip(), 16) for h in raw.split(",") if h.strip())
                    await asyncio.to_thread(_serial_write_sync, seq, device)
                except Exception as exc:
                    self.log.append(f"  serial_send_sequence error: {exc}")
                i += 1

            elif btype == "serial_wait_response":
                match = params.get("match", "")
                timeout_ms = max(100, int(params.get("timeout_ms", 5000)))
                device = Path(params.get("device", str(self.serial)))
                found = await _serial_read_until(match, timeout_ms / 1000.0, device)
                self.log.append(f"  wait_response '{match}': {'found' if found else 'timeout'}")
                i += 1

            # ------------------------------------------------------------------
            # Network (stub — actual daemon management is OS-level)
            # ------------------------------------------------------------------
            elif btype in ("net_provide_dhcp", "net_provide_dns", "net_static_response",
                           "net_log_traffic", "net_respond_ping"):
                result = await self.configfs.configure_network(btype, params)
                self.log.append(f"  network action {btype}: {result}")
                i += 1

            # ------------------------------------------------------------------
            # Gadget profile switching
            # ------------------------------------------------------------------
            elif btype == "gadget_switch_hid":
                mouse = bool(params.get("mouse", True))
                result = await self.configfs.switch_profile("hid", {"mouse": mouse})
                self.log.append(f"  gadget->hid: {result}")
                i += 1

            elif btype == "gadget_switch_serial":
                result = await self.configfs.switch_profile("serial", {})
                self.log.append(f"  gadget->serial: {result}")
                i += 1

            elif btype == "gadget_switch_ethernet":
                mode = params.get("mode", "rndis")
                result = await self.configfs.switch_profile("ethernet", {"mode": mode})
                self.log.append(f"  gadget->ethernet({mode}): {result}")
                i += 1

            elif btype == "gadget_switch_composite":
                raw_funcs = params.get("functions", "hid,serial")
                if isinstance(raw_funcs, str):
                    funcs = [f.strip() for f in raw_funcs.split(",") if f.strip()]
                else:
                    funcs = list(raw_funcs)
                result = await self.configfs.switch_profile("composite", {"functions": funcs})
                self.log.append(f"  gadget->composite{funcs}: {result}")
                i += 1

            elif btype == "gadget_load_from_sd":
                filename = params.get("filename", "")
                path = self.sd / filename
                if path.exists():
                    try:
                        profile_data = json.loads(path.read_text())
                        result = await self.configfs.switch_profile("custom", profile_data)
                        self.log.append(f"  gadget->sd:{filename}: {result}")
                    except Exception as exc:
                        self.log.append(f"  gadget_load_from_sd error: {exc}")
                else:
                    self.log.append(f"  SD profile not found: {filename}")
                i += 1

            else:
                self.log.append(f"  [SKIP] unknown block type: {btype}")
                i += 1

            executed += 1

        return executed

    # ------------------------------------------------------------------
    # Structure helpers
    # ------------------------------------------------------------------

    def _find_if_boundaries(
        self, blocks: List[Dict[str, Any]], start: int, end: int
    ) -> tuple[Optional[int], Optional[int]]:
        """Return (else_idx, end_if_idx) for the current if block starting at `start`."""
        depth = 1
        else_idx: Optional[int] = None
        for i in range(start, end):
            t = blocks[i].get("type", "")
            if t == "if_os":
                depth += 1
            elif t == "end_if":
                depth -= 1
                if depth == 0:
                    return else_idx, i
            elif t == "else_block" and depth == 1:
                else_idx = i
        return else_idx, None

    def _find_end_loop(
        self, blocks: List[Dict[str, Any]], start: int, end: int
    ) -> Optional[int]:
        """Return index of matching end_loop."""
        depth = 1
        for i in range(start, end):
            t = blocks[i].get("type", "")
            if t == "loop_n":
                depth += 1
            elif t == "end_loop":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def set_detected_os(self, os_name: str) -> None:
        """Inject the detected OS name so if_os blocks can branch correctly."""
        self._detected_os = os_name.lower() if os_name else None
