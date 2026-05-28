from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "socket_path": "/run/onikiri/supervisor.sock",
    "log_path": "/userdata/logs/supervisor.log",
    "engagement_data_dir": "/userdata/captures/engagements",
    "overlay_paths": ["/userdata/captures/engagements"],
    "public_mode": True,
    "allow_live_operations": False,
    "mitm_rules_path": "/userdata/config/mitm-rules.json",
    "mitm_ca_dir": "/userdata/config/ca",
    "hid_sequence_path": "/userdata/hid/hid-sequence.json",
    "hid_payload_dir": "/userdata/captures/payloads",
    "usb_device_config_path": "/userdata/config/usb-device.json",
    "ui": {
        "listen": "127.0.0.1",
        "port": 8171,
        "kiosk_command": [],
    },
    "modules": [
        "wifi_recon",
        "mitm",
        "network_scanner",
        "bluetooth_recon",
        "hid_gadget",
        "payload_builder",
        "engagement",
        "system_info",
    ],
}


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    if path is None:
        return deepcopy(DEFAULT_CONFIG)
    config_path = Path(path)
    data = json.loads(config_path.read_text())
    return _merge(DEFAULT_CONFIG, data)
