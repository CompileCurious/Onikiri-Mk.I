"""
Onikiri Mk.I — Wi-Fi Recon Module
Passive scanning, active AP enumeration, and station discovery.
Supports monitor mode and frame injection where the driver allows.

External dependencies: iw, aircrack-ng suite (iwlist fallback)
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from .base_module import BaseModule, ModuleState


class WifiReconModule(BaseModule):
    name = "wifi_recon"
    description = "Wi-Fi reconnaissance: passive scan, AP enumeration, client discovery"
    commands = {
        "scan":          "Active AP scan on interface (iw dev scan)",
        "monitor_start": "Put interface into monitor mode",
        "monitor_stop":  "Return interface to managed mode",
        "airodump":      "Passive capture with airodump-ng",
        "deauth":        "Send deauth frames to target (requires monitor mode + injection)",
        "status":        "Return current interface and mode status",
    }

    async def register(self) -> None:
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "scan":          self._scan,
            "monitor_start": self._monitor_start,
            "monitor_stop":  self._monitor_stop,
            "airodump":      self._airodump,
            "deauth":        self._deauth,
            "status":        self._status,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _scan(self, params: dict) -> dict:
        iface = self._sanitise_iface(params.get("interface", "wlan0"))
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["iw", "dev", iface, "scan"], timeout=30.0
            )
            networks = self._parse_iw_scan(result["stdout"])
            return {"interface": iface, "networks": networks, "raw": result["stdout"]}
        finally:
            self.state = ModuleState.IDLE

    async def _monitor_start(self, params: dict) -> dict:
        iface = self._sanitise_iface(params.get("interface", "wlan0"))
        mon_iface = f"{iface}mon"
        self.state = ModuleState.RUNNING
        # Bring interface down, set monitor mode, bring back up
        await self._run_subprocess(["ip", "link", "set", iface, "down"])
        await self._run_subprocess(["iw", "dev", iface, "set", "type", "monitor"])
        result = await self._run_subprocess(["ip", "link", "set", iface, "up"])
        self.state = ModuleState.IDLE
        return {"monitor_interface": iface, "returncode": result["returncode"]}

    async def _monitor_stop(self, params: dict) -> dict:
        iface = self._sanitise_iface(params.get("interface", "wlan0"))
        self.state = ModuleState.RUNNING
        await self._run_subprocess(["ip", "link", "set", iface, "down"])
        await self._run_subprocess(["iw", "dev", iface, "set", "type", "managed"])
        result = await self._run_subprocess(["ip", "link", "set", iface, "up"])
        self.state = ModuleState.IDLE
        return {"interface": iface, "returncode": result["returncode"]}

    async def _airodump(self, params: dict) -> dict:
        """
        Start airodump-ng capture to a temp file for a given duration.
        Caller can retrieve the capture path for further analysis.
        """
        iface = self._sanitise_iface(params.get("interface", "wlan0"))
        duration = min(int(params.get("duration", 30)), 300)  # max 5 min
        output_prefix = "/tmp/onikiri_capture"
        channel = params.get("channel")

        cmd = ["airodump-ng", "--output-format", "csv",
               "--write", output_prefix]
        if channel:
            channel_str = str(int(channel))  # ensure integer
            cmd += ["--channel", channel_str]
        cmd.append(iface)

        self.state = ModuleState.RUNNING
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.sleep(duration)
            proc.terminate()
            await proc.wait()
            return {
                "capture_file": f"{output_prefix}-01.csv",
                "duration": duration,
            }
        finally:
            self.state = ModuleState.IDLE

    async def _deauth(self, params: dict) -> dict:
        self._require(params, "interface", "bssid")
        iface = self._sanitise_iface(params["interface"])
        bssid = self._sanitise_mac(params["bssid"])
        client = self._sanitise_mac(params.get("client", "FF:FF:FF:FF:FF:FF"))
        count = min(int(params.get("count", 5)), 64)

        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["aireplay-ng", "--deauth", str(count),
                 "-a", bssid, "-c", client, iface],
                timeout=30.0,
            )
            return result
        finally:
            self.state = ModuleState.IDLE

    async def _status(self, params: dict) -> dict:
        iface = self._sanitise_iface(params.get("interface", "wlan0"))
        result = await self._run_subprocess(["iw", "dev", iface, "info"])
        return {"output": result["stdout"], "returncode": result["returncode"]}

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_iw_scan(raw: str) -> list[dict]:
        networks: list[dict] = []
        current: dict = {}
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("BSS "):
                if current:
                    networks.append(current)
                mac = line.split()[1].split("(")[0]
                current = {"bssid": mac, "ssid": "", "signal": None,
                           "freq": None, "security": []}
            elif line.startswith("SSID:"):
                current["ssid"] = line.split(":", 1)[1].strip()
            elif line.startswith("signal:"):
                m = re.search(r"(-?\d+\.\d+)", line)
                if m:
                    current["signal"] = float(m.group(1))
            elif line.startswith("freq:"):
                m = re.search(r"(\d+)", line)
                if m:
                    current["freq"] = int(m.group(1))
            elif "WPA" in line or "RSN" in line:
                proto = "WPA2" if "RSN" in line else "WPA"
                if proto not in current.get("security", []):
                    current.setdefault("security", []).append(proto)
        if current:
            networks.append(current)
        return networks

    @staticmethod
    def _sanitise_mac(mac: str) -> str:
        clean = mac.upper().strip()
        if not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", clean):
            raise ValueError(f"invalid MAC address: {mac!r}")
        return clean
