from __future__ import annotations

import asyncio
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.hid.schema import MODIFIER_BITS, NAMED_KEYS, char_to_hid

# USB HID device paths
_KBD_DEVICE = Path("/dev/hidg0")
_MOUSE_DEVICE = Path("/dev/hidg1")


# ---------------------------------------------------------------------------
# Low-level HID report writers (blocking — run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _send_keyboard_report(modifier: int, scancode: int, device: Path) -> None:
    """Write an 8-byte keyboard report to the HID device."""
    if not device.exists():
        return
    report = bytes([modifier, 0, scancode, 0, 0, 0, 0, 0])
    with device.open("wb") as dev:
        dev.write(report)


def _send_mouse_report(buttons: int, x: int, y: int, scroll: int, device: Path) -> None:
    """Write a 4-byte mouse report: [buttons, x_rel, y_rel, scroll]."""
    if not device.exists():
        return
    # x, y, scroll are signed 8-bit
    report = struct.pack("4b", buttons, max(-127, min(127, x)),
                         max(-127, min(127, y)), max(-127, min(127, scroll)))
    with device.open("wb") as dev:
        dev.write(report)


# ---------------------------------------------------------------------------
# Async key helpers
# ---------------------------------------------------------------------------

async def _key_tap(modifier: int, scancode: int, device: Path, delay_s: float = 0.02) -> None:
    if scancode == 0:
        return
    await asyncio.to_thread(_send_keyboard_report, modifier, scancode, device)
    await asyncio.sleep(delay_s)
    await asyncio.to_thread(_send_keyboard_report, 0, 0, device)
    await asyncio.sleep(delay_s)


async def _type_text(text: str, delay_ms: int, device: Path) -> int:
    delay_s = max(1, delay_ms) / 1000.0
    count = 0
    for ch in text:
        modifier, scancode = char_to_hid(ch)
        if scancode == 0:
            continue
        await _key_tap(modifier, scancode, device, delay_s)
        count += 1
    return count


def _resolve_key(key_str: str) -> int:
    """Return scancode for a key name (case-insensitive, normalised)."""
    return NAMED_KEYS.get(key_str.upper().strip(), 0)


def _resolve_modifiers(mods: list[str]) -> int:
    result = 0
    for m in mods:
        result |= MODIFIER_BITS.get(m.upper().strip(), 0)
    return result


# ---------------------------------------------------------------------------
# Block Execution Engine
# ---------------------------------------------------------------------------

class BlockEngine:
    """
    Executes an ordered list of HID blocks against a USB HID device.
    Call `run()` to start and check `is_running` / call `stop()` to cancel.
    """

    def __init__(
        self,
        blocks: List[Dict[str, Any]],
        kbd_device: Path = _KBD_DEVICE,
        mouse_device: Path = _MOUSE_DEVICE,
    ) -> None:
        self.blocks = [b for b in blocks if b.get("enabled", True)]
        self.kbd = kbd_device
        self.mouse = mouse_device
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop_event = asyncio.Event()
        self.log: List[str] = []

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()

    async def run(self) -> Dict[str, Any]:
        """Execute blocks and return a summary dict."""
        self._stop_event.clear()
        self.log = []
        try:
            executed = await self._run_blocks(self.blocks, 0, len(self.blocks))
            return {"status": "completed", "executed": executed, "log": self.log}
        except asyncio.CancelledError:
            return {"status": "stopped", "log": self.log}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "log": self.log}

    async def _run_blocks(self, blocks: List[Dict[str, Any]], start: int, end: int) -> int:
        """Run blocks[start:end], returns count of blocks executed."""
        i = start
        executed = 0
        loop_stack: List[tuple[int, int]] = []  # (loop_start_idx, remaining)

        while i < end:
            if self._stop_event.is_set():
                break
            block = blocks[i]
            btype = block.get("type", "")
            params = block.get("params", {})
            self.log.append(f"[{i}] {btype}")

            if btype == "delay":
                ms = int(params.get("ms", 500))
                await asyncio.sleep(ms / 1000.0)

            elif btype == "wait_window":
                ms = int(params.get("timeout_ms", 2000))
                await asyncio.sleep(ms / 1000.0)

            elif btype == "type_text":
                text = params.get("text", "")
                delay_ms = int(params.get("delay_ms", 20))
                await _type_text(text, delay_ms, self.kbd)

            elif btype == "press_key":
                sc = _resolve_key(params.get("key", ""))
                await _key_tap(0, sc, self.kbd)

            elif btype == "hold_key":
                sc = _resolve_key(params.get("key", ""))
                await asyncio.to_thread(_send_keyboard_report, 0, sc, self.kbd)

            elif btype == "release_key":
                await asyncio.to_thread(_send_keyboard_report, 0, 0, self.kbd)

            elif btype == "key_combo":
                mods_raw = params.get("modifiers", [])
                if isinstance(mods_raw, str):
                    mods_raw = [m.strip() for m in mods_raw.split("+") if m.strip()]
                modifier = _resolve_modifiers(mods_raw)
                sc = _resolve_key(params.get("key", ""))
                await _key_tap(modifier, sc, self.kbd)

            elif btype == "mouse_move":
                x = int(params.get("x", 0))
                y = int(params.get("y", 0))
                # Send in chunks of 127 for large movements
                while abs(x) > 0 or abs(y) > 0:
                    dx = max(-127, min(127, x))
                    dy = max(-127, min(127, y))
                    await asyncio.to_thread(_send_mouse_report, 0, dx, dy, 0, self.mouse)
                    x -= dx
                    y -= dy
                    await asyncio.sleep(0.01)

            elif btype == "mouse_click":
                btn_map = {"left": 1, "right": 2, "middle": 4}
                btn = btn_map.get(params.get("button", "left"), 1)
                await asyncio.to_thread(_send_mouse_report, btn, 0, 0, 0, self.mouse)
                await asyncio.sleep(0.05)
                await asyncio.to_thread(_send_mouse_report, 0, 0, 0, 0, self.mouse)

            elif btype == "mouse_scroll":
                direction = params.get("direction", "down")
                amount = int(params.get("amount", 3))
                delta = -amount if direction == "down" else amount
                await asyncio.to_thread(_send_mouse_report, 0, 0, 0, delta, self.mouse)

            elif btype == "loop_start":
                count = max(1, int(params.get("count", 1)))
                loop_stack.append((i, count - 1))

            elif btype == "loop_end":
                if loop_stack:
                    start_idx, remaining = loop_stack[-1]
                    if remaining > 0:
                        loop_stack[-1] = (start_idx, remaining - 1)
                        i = start_idx + 1
                        continue
                    else:
                        loop_stack.pop()

            elif btype == "if_condition":
                # Cannot interrogate the target host; treat as pass-through
                pass

            elif btype in ("else_block", "endif"):
                pass

            elif btype == "open_run":
                target_os = params.get("target_os", "windows")
                if target_os == "windows":
                    await _key_tap(MODIFIER_BITS["GUI"], NAMED_KEYS["R"], self.kbd)
                elif target_os == "linux":
                    await _key_tap(MODIFIER_BITS["ALT"], NAMED_KEYS["F2"], self.kbd)
                elif target_os == "macos":
                    await _key_tap(MODIFIER_BITS["META"], NAMED_KEYS["SPACE"], self.kbd)

            elif btype == "open_terminal":
                target_os = params.get("target_os", "windows")
                if target_os == "windows":
                    await _key_tap(MODIFIER_BITS["GUI"], NAMED_KEYS["R"], self.kbd)
                    await asyncio.sleep(0.5)
                    await _type_text("cmd\n", 20, self.kbd)
                elif target_os == "linux":
                    await _key_tap(
                        MODIFIER_BITS["CTRL"] | MODIFIER_BITS["ALT"],
                        NAMED_KEYS["T"], self.kbd,
                    )
                elif target_os == "macos":
                    await _key_tap(MODIFIER_BITS["META"], NAMED_KEYS["SPACE"], self.kbd)
                    await asyncio.sleep(0.5)
                    await _type_text("Terminal\n", 20, self.kbd)

            elif btype == "paste_clipboard":
                target_os = params.get("target_os", "windows")
                if target_os == "macos":
                    modifier = MODIFIER_BITS["META"]
                else:
                    modifier = MODIFIER_BITS["CTRL"]
                await _key_tap(modifier, NAMED_KEYS["V"], self.kbd)

            executed += 1
            i += 1

        return executed

    def start_background(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Schedule run() as a background task on the running event loop."""
        self._task = asyncio.ensure_future(self.run())
