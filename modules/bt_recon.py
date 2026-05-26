"""
Onikiri Mk.I — Bluetooth Recon Module
Classic BT and BLE device enumeration, service discovery.

External dependencies: bluetoothctl, hcitool, sdptool, btlejuice (optional)
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from .base_module import BaseModule, ModuleState


class BluetoothReconModule(BaseModule):
    name = "bt_recon"
    description = "Bluetooth recon: device enumeration, BLE scanning, service discovery"
    commands = {
        "scan_classic": "Scan for discoverable Classic BT devices",
        "scan_ble":     "BLE advertisement scanning (passive)",
        "sdp_browse":   "SDP service record query on a Classic BT device",
        "info":         "Retrieve device info for a given address",
        "hci_status":   "Return HCI adapter status",
    }

    async def register(self) -> None:
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "scan_classic": self._scan_classic,
            "scan_ble":     self._scan_ble,
            "sdp_browse":   self._sdp_browse,
            "info":         self._info,
            "hci_status":   self._hci_status,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _scan_classic(self, params: dict) -> dict:
        duration = min(int(params.get("duration", 10)), 60)
        hci = self._sanitise_hci(params.get("hci", "hci0"))
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["hcitool", "-i", hci, "scan", "--flush"],
                timeout=float(duration + 5),
            )
            devices = self._parse_hcitool_scan(result["stdout"])
            return {"devices": devices, "hci": hci}
        finally:
            self.state = ModuleState.IDLE

    async def _scan_ble(self, params: dict) -> dict:
        duration = min(int(params.get("duration", 10)), 60)
        hci = self._sanitise_hci(params.get("hci", "hci0"))
        self.state = ModuleState.RUNNING
        try:
            # Enable LE scanning
            await self._run_subprocess(
                ["hcitool", "-i", hci, "lescan", "--passive"],
                timeout=float(duration),
            )
            # Read from btmon or lescan output — simplified capture
            result = await self._run_subprocess(
                ["hcidump", "-i", hci, "-X"], timeout=float(duration)
            )
            return {"raw": result["stdout"][:4096]}  # cap output
        finally:
            self.state = ModuleState.IDLE

    async def _sdp_browse(self, params: dict) -> dict:
        self._require(params, "address")
        addr = self._sanitise_bt_addr(params["address"])
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["sdptool", "browse", "--xml", addr], timeout=30.0
            )
            return {"address": addr, "sdp_xml": result["stdout"]}
        finally:
            self.state = ModuleState.IDLE

    async def _info(self, params: dict) -> dict:
        self._require(params, "address")
        addr = self._sanitise_bt_addr(params["address"])
        result = await self._run_subprocess(
            ["hcitool", "info", addr], timeout=10.0
        )
        return {"address": addr, "output": result["stdout"]}

    async def _hci_status(self, params: dict) -> dict:
        hci = self._sanitise_hci(params.get("hci", "hci0"))
        result = await self._run_subprocess(["hciconfig", hci, "detail"])
        return {"output": result["stdout"]}

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_hcitool_scan(raw: str) -> list[dict]:
        devices = []
        for line in raw.splitlines():
            line = line.strip()
            m = re.match(r"([0-9A-F:]{17})\s+(.*)", line, re.IGNORECASE)
            if m:
                devices.append({"address": m.group(1).upper(), "name": m.group(2).strip()})
        return devices

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_bt_addr(addr: str) -> str:
        clean = addr.upper().strip()
        if not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", clean):
            raise ValueError(f"invalid Bluetooth address: {addr!r}")
        return clean

    @staticmethod
    def _sanitise_hci(hci: str) -> str:
        if not re.fullmatch(r"hci\d+", hci):
            raise ValueError(f"invalid HCI device: {hci!r}")
        return hci
