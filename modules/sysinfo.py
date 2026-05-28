"""
Onikiri Mk.I — System Info & Diagnostics Module
Exposes hardware metrics, network state, storage, and self-test functions.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .base_module import BaseModule, ModuleState


class SysInfoModule(BaseModule):
    name = "sysinfo"
    description = "System info and diagnostics: CPU, memory, storage, network, self-test"
    commands = {
        "overview":       "Full system snapshot",
        "cpu":            "CPU usage and temperature",
        "memory":         "RAM and swap usage",
        "storage":        "Disk usage and partition info",
        "network":        "Network interface states and addresses",
        "uptime":         "System uptime and load averages",
        "interfaces":     "List all network interfaces",
        "self_test":      "Verify core components are accessible",
        "battery":        "Battery / power bank state (if detectable)",
    }

    async def register(self) -> None:
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "overview":  self._overview,
            "cpu":       self._cpu,
            "memory":    self._memory,
            "storage":   self._storage,
            "network":   self._network,
            "uptime":    self._uptime,
            "interfaces":self._interfaces,
            "self_test": self._self_test,
            "battery":   self._battery,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _overview(self, _params: dict) -> dict:
        return {
            "cpu":     await self._cpu({}),
            "memory":  await self._memory({}),
            "storage": await self._storage({}),
            "uptime":  await self._uptime({}),
            "network": await self._interfaces({}),
        }

    async def _cpu(self, _params: dict) -> dict:
        # Read /proc/stat for CPU time
        stat_a = self._read_cpu_stat()
        time.sleep(0.1)
        stat_b = self._read_cpu_stat()

        idle_a = stat_a[3] + stat_a[4]
        idle_b = stat_b[3] + stat_b[4]
        total_a = sum(stat_a)
        total_b = sum(stat_b)
        delta_total = total_b - total_a
        delta_idle  = idle_b  - idle_a
        usage = 0.0 if delta_total == 0 else (1 - delta_idle / delta_total) * 100.0

        temp = self._read_cpu_temp()
        return {
            "usage_pct": round(usage, 1),
            "temp_c": temp,
            "cores": os.cpu_count(),
        }

    async def _memory(self, _params: dict) -> dict:
        data = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split()
            if parts:
                data[parts[0].rstrip(":")] = int(parts[1]) if len(parts) > 1 else 0
        total = data.get("MemTotal", 0)
        free  = data.get("MemAvailable", 0)
        used  = total - free
        return {
            "total_kb": total,
            "used_kb": used,
            "free_kb": free,
            "usage_pct": round(used / total * 100, 1) if total else 0,
            "swap_total_kb": data.get("SwapTotal", 0),
            "swap_used_kb": data.get("SwapTotal", 0) - data.get("SwapFree", 0),
        }

    async def _storage(self, _params: dict) -> dict:
        result = await self._run_subprocess(["df", "-h", "--output=source,size,used,avail,pcent,target"])
        lines = result["stdout"].splitlines()[1:]
        partitions = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 6:
                partitions.append({
                    "device": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "avail": parts[3],
                    "use_pct": parts[4],
                    "mount": parts[5],
                })
        return {"partitions": partitions}

    async def _network(self, _params: dict) -> dict:
        result = await self._run_subprocess(["ip", "-j", "addr"])
        try:
            import json
            return {"interfaces": json.loads(result["stdout"])}
        except Exception:
            return {"raw": result["stdout"]}

    async def _uptime(self, _params: dict) -> dict:
        raw = Path("/proc/uptime").read_text().split()
        uptime_s = float(raw[0])
        load = Path("/proc/loadavg").read_text().split()[:3]
        return {
            "uptime_s": uptime_s,
            "load_1":  float(load[0]),
            "load_5":  float(load[1]),
            "load_15": float(load[2]),
        }

    async def _interfaces(self, _params: dict) -> dict:
        result = await self._run_subprocess(["ip", "link", "show"])
        ifaces = re.findall(r"\d+: (\w+):", result["stdout"])
        return {"interfaces": ifaces}

    async def _self_test(self, _params: dict) -> dict:
        checks = {}
        # IPC socket
        from pathlib import Path as P
        checks["ipc_socket"] = P("/run/onikiri/supervisor.sock").exists()
        # /userdata writable
        try:
            test_path = Path("/userdata/.self_test")
            test_path.write_text("ok")
            test_path.unlink()
            checks["data_writable"] = True
        except OSError:
            checks["data_writable"] = False
        # nmap present
        result = await self._run_subprocess(["which", "nmap"])
        checks["nmap"] = result["returncode"] == 0
        # iw present
        result = await self._run_subprocess(["which", "iw"])
        checks["iw"] = result["returncode"] == 0
        # python3 present (always true if we're running)
        checks["python3"] = True
        return {"checks": checks, "all_ok": all(checks.values())}

    async def _battery(self, _params: dict) -> dict:
        # AXP chip exposes power supply info via sysfs
        power_dir = Path("/sys/class/power_supply")
        if not power_dir.exists():
            return {"available": False}
        supplies = []
        for p in power_dir.iterdir():
            info: dict = {"name": p.name}
            for attr in ("status", "capacity", "voltage_now", "current_now"):
                f = p / attr
                if f.exists():
                    info[attr] = f.read_text().strip()
            supplies.append(info)
        return {"available": bool(supplies), "supplies": supplies}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _read_cpu_stat() -> list[int]:
        line = Path("/proc/stat").read_text().splitlines()[0]
        return [int(x) for x in line.split()[1:]]

    @staticmethod
    def _read_cpu_temp() -> float | None:
        # Allwinner thermal zone
        for i in range(4):
            p = Path(f"/sys/class/thermal/thermal_zone{i}/temp")
            if p.exists():
                try:
                    return float(p.read_text().strip()) / 1000.0
                except ValueError:
                    pass
        return None
