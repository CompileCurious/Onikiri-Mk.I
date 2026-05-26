from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import subprocess
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from onikiri.config import load_config
from onikiri.ipc import IPCClient


class BridgeState:
    def __init__(self, socket_path: str, config: Dict[str, Any]) -> None:
        self.socket_path = socket_path
        self.config = config
        self.asset_dir = Path(__file__).resolve().parent / "assets"

    def request(self, action: str, **payload: Any) -> Dict[str, Any]:
        return asyncio.run(IPCClient(self.socket_path).request(action, **payload))


class BridgeHandler(SimpleHTTPRequestHandler):
    state: BridgeState

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(self.state.asset_dir), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            payload = {
                "modules": self.state.request("list_modules").get("modules", []),
                "jobs": self.state.request("list_jobs").get("jobs", []),
            }
            self.respond(payload)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body)
        if parsed.path == "/api/run":
            response = self.state.request(
                "run_module",
                module=payload["module"],
                module_action=payload.get("module_action"),
                params=payload.get("params", {}),
            )
            self.respond(response)
            return
        if parsed.path == "/api/wipe":
            response = self.state.request("wipe_engagement_data")
            self.respond(response)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def respond(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def serve(socket_path: str, config: Dict[str, Any]) -> None:
    listen = config["ui"]["listen"]
    port = int(config["ui"]["port"])
    state = BridgeState(socket_path=socket_path, config=config)
    handler = type("OnikiriBridgeHandler", (BridgeHandler,), {"state": state})
    server = ThreadingHTTPServer((listen, port), handler)
    kiosk_command = config["ui"].get("kiosk_command") or []
    kiosk_process: subprocess.Popen[Any] | None = None
    try:
        if kiosk_command:
            kiosk_process = subprocess.Popen(kiosk_command)
        server.serve_forever()
    finally:
        server.server_close()
        if kiosk_process is not None:
            kiosk_process.terminate()
            kiosk_process.wait(timeout=5)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Onikiri Mk.I UI bridge")
    parser.add_argument("--config", default="configs/onikiri-supervisor.json")
    parser.add_argument("--socket", default="/run/onikiri/supervisor.sock")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    config = load_config(args.config)
    serve(args.socket, config)


if __name__ == "__main__":
    main()
