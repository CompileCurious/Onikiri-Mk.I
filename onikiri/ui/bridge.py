from __future__ import annotations

import argparse
import asyncio
import glob as _glob
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


def _detect_hardware() -> Dict[str, bool]:
    """Probe the system for known offensive hardware adapters via lsusb."""
    hw: Dict[str, bool] = {
        "alfa_wifi": False,
        "bluetooth": False,
        "rtlsdr": False,
        "nfc": False,
        "serial": False,
    }
    try:
        out = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=3
        ).stdout.lower()
        # Realtek / Mediatek / Ralink — covers Alfa AWUS adapters and common offensive Wi-Fi
        if any(v in out for v in ("0bda:", "0e8d:", "148f:", "2357:", "7392:")):
            hw["alfa_wifi"] = True
        # Bluetooth dongles: CSR, Broadcom, Intel, Realtek, Atheros
        if any(v in out for v in ("0a12:", "8087:0a2b", "0bda:b00", "13d3:", "0cf3:")):
            hw["bluetooth"] = True
        # RTL-SDR v3 / RTL2832U generic
        if "0bda:2832" in out or "0bda:2838" in out:
            hw["rtlsdr"] = True
        # ACR122U / PN532 / Sony NFC/RFID readers
        if any(v in out for v in ("072f:2200", "04e6:5591", "054c:06c1", "04cc:2533")):
            hw["nfc"] = True
    except Exception:
        pass
    if _glob.glob("/dev/ttyUSB*") or _glob.glob("/dev/ttyACM*"):
        hw["serial"] = True
    return hw


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
                "hardware": _detect_hardware(),
            }
            self.respond(payload)
            return
        if parsed.path == "/api/mitm/state":
            status = self.state.request("mitm_status")
            rules_resp = self.state.request("mitm_list_rules")
            vectors_resp = self.state.request("mitm_list_vectors")
            payload = {
                "status": status.get("status", "inactive"),
                "running": status.get("running", False),
                "active_params": status.get("active_params", {}),
                "tools": status.get("tools", {}),
                "rules": rules_resp.get("rules", []),
                "schema": rules_resp.get("schema", {}),
                "vectors": vectors_resp.get("vectors", []),
            }
            self.respond(payload)
            return
        if parsed.path == "/api/hid/state":
            status = self.state.request("hid_status")
            blocks_resp = self.state.request("hid_list_blocks")
            devices_resp = self.state.request("hid_list_devices")
            payload = {
                "status": status.get("status", "inactive"),
                "running": status.get("running", False),
                "device_profile": status.get("device_profile", "generic_keyboard"),
                "sequence_name": status.get("sequence_name", "default"),
                "kbd_present": status.get("kbd_present", False),
                "blocks": blocks_resp.get("blocks", []),
                "meta": blocks_resp.get("meta", {}),
                "schema": blocks_resp.get("schema", {}),
                "devices": devices_resp.get("devices", {}),
            }
            self.respond(payload)
            return
        if parsed.path == "/api/hid/sd/list":
            response = self.state.request("hid_sd_list")
            self.respond(response)
            return
        if parsed.path == "/api/gadget/state":
            status = self.state.request("gadget_auto_status")
            manifest = self.state.request("gadget_auto_manifest")
            workflows = self.state.request("gadget_auto_list_workflows")
            gadget = self.state.request("gadget_auto_get_gadget_state")
            payload = {
                "status": status.get("status", "inactive"),
                "running": status.get("running", False),
                "active_workflow_id": status.get("active_workflow_id"),
                "gadget_profile": gadget.get("current_profile"),
                "schema": manifest.get("schema", {}),
                "workflows": workflows.get("workflows", []),
            }
            self.respond(payload)
            return
        if parsed.path == "/api/gadget/sd/list":
            response = self.state.request("gadget_auto_sd_list")
            self.respond(response)
            return
        if parsed.path == "/api/gadget/logs":
            response = self.state.request("gadget_auto_get_logs")
            self.respond(response)
            return
        if parsed.path == "/api/gadget/payload/list":
            response = self.state.request("gadget_auto_payload_list")
            self.respond(response)
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
        # ------------------------------------------------------------------
        # MITM rule-engine and control endpoints
        # ------------------------------------------------------------------
        if parsed.path == "/api/mitm/rules/add":
            response = self.state.request("mitm_add_rule", rule=payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/rules/remove":
            response = self.state.request("mitm_remove_rule", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/rules/toggle":
            response = self.state.request("mitm_toggle_rule", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/rules/reorder":
            response = self.state.request("mitm_reorder_rules", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/rules/move_up":
            response = self.state.request("mitm_move_rule_up", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/rules/move_down":
            response = self.state.request("mitm_move_rule_down", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/rules/test":
            response = self.state.request("mitm_test_rule", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/start":
            response = self.state.request("mitm_start", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/mitm/stop":
            response = self.state.request("mitm_stop")
            self.respond(response)
            return
        if parsed.path == "/api/mitm/generate_ca":
            response = self.state.request("mitm_generate_ca", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/blocks/add":
            response = self.state.request("hid_add_block", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/blocks/remove":
            response = self.state.request("hid_remove_block", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/blocks/toggle":
            response = self.state.request("hid_toggle_block", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/blocks/reorder":
            response = self.state.request("hid_reorder_blocks", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/blocks/move_up":
            response = self.state.request("hid_move_block_up", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/blocks/move_down":
            response = self.state.request("hid_move_block_down", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/device/set":
            response = self.state.request("hid_set_device", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/device/add":
            response = self.state.request("hid_add_device", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/device/remove":
            response = self.state.request("hid_delete_device", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/setup_gadget":
            response = self.state.request("hid_setup_gadget", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/teardown_gadget":
            response = self.state.request("hid_teardown_gadget", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/start":
            response = self.state.request("hid_start", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/stop":
            response = self.state.request("hid_stop", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/sd/preview":
            response = self.state.request("hid_sd_preview", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/sd/import":
            response = self.state.request("hid_sd_import", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/sd/run_raw":
            response = self.state.request("hid_sd_run_raw", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/hid/export":
            response = self.state.request("hid_export", **payload)
            self.respond(response)
            return
        # ------------------------------------------------------------------
        # Gadget Automation endpoints
        # ------------------------------------------------------------------
        if parsed.path == "/api/gadget/workflow/save":
            response = self.state.request("gadget_auto_save_workflow", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/workflow/delete":
            response = self.state.request("gadget_auto_delete_workflow", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/workflow/get":
            response = self.state.request("gadget_auto_get_workflow", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/workflow/validate":
            response = self.state.request("gadget_auto_validate", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/workflow/run":
            response = self.state.request("gadget_auto_run_workflow", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/workflow/stop":
            response = self.state.request("gadget_auto_stop_workflow")
            self.respond(response)
            return
        if parsed.path == "/api/gadget/workflow/blocks/replace":
            response = self.state.request("gadget_auto_replace_blocks", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/sd/preview":
            response = self.state.request("gadget_auto_sd_preview", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/sd/import":
            response = self.state.request("gadget_auto_sd_import", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/sd/export":
            response = self.state.request("gadget_auto_sd_export", **payload)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/teardown":
            response = self.state.request("gadget_auto_gadget_teardown")
            self.respond(response)
            return
        if parsed.path == "/api/gadget/payload/create":
            size_mb = int(payload.get("size_mb", 64))
            response = self.state.request("gadget_auto_payload_create", size_mb=size_mb)
            self.respond(response)
            return
        if parsed.path == "/api/gadget/payload/add":
            response = self.state.request(
                "gadget_auto_payload_add_file",
                filename=payload.get("filename", ""),
                data_b64=payload.get("data_b64", ""),
            )
            self.respond(response)
            return
        if parsed.path == "/api/gadget/payload/clear":
            response = self.state.request("gadget_auto_payload_clear")
            self.respond(response)
            return
        if parsed.path == "/api/stop_module":
            label = payload.get("label", "")
            _STOP_MAP: Dict[str, str] = {
                "MITM":       "mitm_stop",
                "USB GADGET": "gadget_auto_stop_workflow",
                "WI-FI":      "wifi_recon_stop",
                "AUTO-RECON": "network_scanner_stop",
                "BLE/NFC":    "bluetooth_recon_stop",
            }
            action = _STOP_MAP.get(label)
            if action:
                try:
                    response = self.state.request(action)
                except Exception as exc:  # pragma: no cover
                    response = {"status": "error", "error": str(exc)}
            else:
                response = {"status": "ok", "info": "no stop action registered for this module"}
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
