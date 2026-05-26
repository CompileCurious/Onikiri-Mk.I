"""
Onikiri Mk.I — Network Scanning Module
Wrappers around nmap and masscan for host/service discovery.

External dependencies: nmap, masscan
"""

from __future__ import annotations

import ipaddress
import re
import xml.etree.ElementTree as ET
from typing import Any

from .base_module import BaseModule, ModuleState


class NetScanModule(BaseModule):
    name = "net_scan"
    description = "Network scanning: host discovery and service enumeration"
    commands = {
        "ping_sweep":    "ICMP ping sweep across a CIDR range",
        "port_scan":     "TCP/UDP port scan with nmap",
        "service_scan":  "Service/version detection on open ports",
        "masscan":       "High-speed port scan with masscan",
        "os_detect":     "OS fingerprinting (requires root)",
        "vuln_scan":     "nmap NSE vulnerability scripts",
    }

    async def register(self) -> None:
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "ping_sweep":   self._ping_sweep,
            "port_scan":    self._port_scan,
            "service_scan": self._service_scan,
            "masscan":      self._masscan,
            "os_detect":    self._os_detect,
            "vuln_scan":    self._vuln_scan,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _ping_sweep(self, params: dict) -> dict:
        self._require(params, "target")
        target = self._sanitise_target(params["target"])
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["nmap", "-sn", "-oX", "-", target], timeout=120.0
            )
            hosts = self._parse_nmap_xml(result["stdout"])
            return {"target": target, "hosts": hosts}
        finally:
            self.state = ModuleState.IDLE

    async def _port_scan(self, params: dict) -> dict:
        self._require(params, "target")
        target = self._sanitise_target(params["target"])
        ports = self._sanitise_ports(params.get("ports", "1-1024"))
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["nmap", "-sS", "-p", ports, "-oX", "-", "--open", target],
                timeout=300.0,
            )
            return {
                "target": target,
                "ports": ports,
                "hosts": self._parse_nmap_xml(result["stdout"]),
            }
        finally:
            self.state = ModuleState.IDLE

    async def _service_scan(self, params: dict) -> dict:
        self._require(params, "target")
        target = self._sanitise_target(params["target"])
        ports = self._sanitise_ports(params.get("ports", "1-65535"))
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["nmap", "-sV", "-p", ports, "-oX", "-", "--open", target],
                timeout=600.0,
            )
            return {"target": target, "hosts": self._parse_nmap_xml(result["stdout"])}
        finally:
            self.state = ModuleState.IDLE

    async def _masscan(self, params: dict) -> dict:
        self._require(params, "target")
        target = self._sanitise_target(params["target"])
        ports = self._sanitise_ports(params.get("ports", "0-65535"))
        rate = min(int(params.get("rate", 10000)), 100000)

        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["masscan", target, "-p", ports,
                 "--rate", str(rate), "-oL", "-"],
                timeout=600.0,
            )
            open_ports = self._parse_masscan_list(result["stdout"])
            return {"target": target, "open_ports": open_ports}
        finally:
            self.state = ModuleState.IDLE

    async def _os_detect(self, params: dict) -> dict:
        self._require(params, "target")
        target = self._sanitise_target(params["target"])
        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["nmap", "-O", "--osscan-guess", "-oX", "-", target],
                timeout=120.0,
            )
            return {"target": target, "hosts": self._parse_nmap_xml(result["stdout"])}
        finally:
            self.state = ModuleState.IDLE

    async def _vuln_scan(self, params: dict) -> dict:
        self._require(params, "target")
        target = self._sanitise_target(params["target"])
        scripts = params.get("scripts", "vuln")
        # Whitelist safe script categories only
        allowed_cats = {"vuln", "auth", "default", "safe", "discovery"}
        if scripts not in allowed_cats and not scripts.startswith("http-"):
            raise ValueError(f"script category not permitted: {scripts!r}")

        self.state = ModuleState.RUNNING
        try:
            result = await self._run_subprocess(
                ["nmap", f"--script={scripts}", "-oX", "-", target],
                timeout=300.0,
            )
            return {"target": target, "hosts": self._parse_nmap_xml(result["stdout"])}
        finally:
            self.state = ModuleState.IDLE

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_nmap_xml(xml_str: str) -> list[dict]:
        hosts = []
        if not xml_str.strip():
            return hosts
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return hosts
        for host in root.findall("host"):
            addr_el = host.find("address[@addrtype='ipv4']")
            if addr_el is None:
                continue
            entry: dict = {"ip": addr_el.get("addr"), "ports": [], "os": None}
            for port in host.findall(".//port"):
                state_el = port.find("state")
                if state_el is not None and state_el.get("state") == "open":
                    svc = port.find("service")
                    entry["ports"].append({
                        "port": int(port.get("portid", 0)),
                        "proto": port.get("protocol"),
                        "service": svc.get("name") if svc is not None else None,
                        "version": svc.get("version") if svc is not None else None,
                    })
            os_el = host.find(".//osmatch")
            if os_el is not None:
                entry["os"] = {"name": os_el.get("name"), "accuracy": os_el.get("accuracy")}
            hosts.append(entry)
        return hosts

    @staticmethod
    def _parse_masscan_list(raw: str) -> list[dict]:
        results = []
        for line in raw.splitlines():
            if line.startswith("open"):
                parts = line.split()
                if len(parts) >= 4:
                    results.append({
                        "proto": parts[1],
                        "port": int(parts[2]),
                        "ip": parts[3],
                    })
        return results

    # ── Input validation ──────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_target(target: str) -> str:
        target = target.strip()
        try:
            ipaddress.ip_network(target, strict=False)
            return target
        except ValueError:
            pass
        try:
            ipaddress.ip_address(target)
            return target
        except ValueError:
            pass
        # Hostname: allow alphanumeric, dots, hyphens only
        if re.fullmatch(r"[a-zA-Z0-9.\-]+", target):
            return target
        raise ValueError(f"invalid target: {target!r}")

    @staticmethod
    def _sanitise_ports(ports: str) -> str:
        ports = ports.strip()
        if re.fullmatch(r"[\d,\-]+", ports):
            return ports
        raise ValueError(f"invalid port specification: {ports!r}")
