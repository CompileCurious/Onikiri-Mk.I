from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Workflow schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Trigger types
# ---------------------------------------------------------------------------

TRIGGER_TYPES: Dict[str, str] = {
    "manual":               "Manual (run on demand)",
    "usb_hid":              "USB: Host loads HID",
    "usb_serial":           "USB: Host loads Serial",
    "usb_rndis":            "USB: Host loads RNDIS/ECM",
    "usb_mass_storage":     "USB: Mass storage LUN mounted",
    "serial_open":          "Serial port opened",
    "network_up":           "Network interface up",
    "hid_idle":             "HID idle",
    "hid_active":           "HID active",
}

# ---------------------------------------------------------------------------
# Block categories
# ---------------------------------------------------------------------------

BLOCK_CATEGORIES: Dict[str, Dict[str, str]] = {
    "flow": {
        "label": "Flow Control",
        "types": [
            "if_os",
            "else_block",
            "end_if",
            "loop_n",
            "end_loop",
            "stop_workflow",
        ],
    },
    "hid": {
        "label": "HID Actions",
        "types": [
            "hid_type_text",
            "hid_press_key",
            "hid_key_combo",
            "hid_mouse_move",
            "hid_mouse_click",
            "hid_scroll",
            "hid_paste_from_sd",
            "hid_upload_from_sd",
            "hid_download_file",
        ],
    },
    "serial": {
        "label": "Serial Actions",
        "types": [
            "serial_send_string",
            "serial_send_sequence",
            "serial_wait_response",
        ],
    },
    "network": {
        "label": "Network Actions",
        "types": [
            "net_provide_dhcp",
            "net_provide_dns",
            "net_static_response",
            "net_log_traffic",
            "net_respond_ping",
        ],
    },
    "gadget": {
        "label": "Gadget Profile",
        "types": [
            "gadget_switch_hid",
            "gadget_switch_serial",
            "gadget_switch_ethernet",
            "gadget_switch_composite",
            "gadget_load_from_sd",
        ],
    },
    "timing": {
        "label": "Timing",
        "types": [
            "delay",
            "wait_event",
        ],
    },
}

# ---------------------------------------------------------------------------
# Block type definitions — label, parameter schema
# ---------------------------------------------------------------------------

# Each parameter entry: (key, label, type, default, required)
# type: "text" | "textarea" | "number" | "select" | "checkbox"

OS_OPTIONS = ["windows", "linux", "macos", "android", "ios"]

BLOCK_TYPES: Dict[str, Dict[str, Any]] = {
    # ------------------------------------------------------------------
    # Flow
    # ------------------------------------------------------------------
    "if_os": {
        "label": "IF OS =",
        "category": "flow",
        "params": [
            {"key": "os", "label": "OS", "type": "select",
             "options": OS_OPTIONS, "required": True},
        ],
    },
    "else_block": {
        "label": "ELSE",
        "category": "flow",
        "params": [],
    },
    "end_if": {
        "label": "END IF",
        "category": "flow",
        "params": [],
    },
    "loop_n": {
        "label": "LOOP N TIMES",
        "category": "flow",
        "params": [
            {"key": "count", "label": "REPEAT COUNT", "type": "number",
             "default": 3, "required": True},
        ],
    },
    "end_loop": {
        "label": "END LOOP",
        "category": "flow",
        "params": [],
    },
    "stop_workflow": {
        "label": "STOP WORKFLOW",
        "category": "flow",
        "params": [],
    },
    # ------------------------------------------------------------------
    # HID
    # ------------------------------------------------------------------
    "hid_type_text": {
        "label": "Type Text",
        "category": "hid",
        "params": [
            {"key": "text", "label": "TEXT", "type": "textarea", "required": True},
            {"key": "delay_ms", "label": "DELAY (ms)", "type": "number", "default": 20},
        ],
    },
    "hid_press_key": {
        "label": "Press Key",
        "category": "hid",
        "params": [
            {"key": "key", "label": "KEY NAME", "type": "text", "required": True},
        ],
    },
    "hid_key_combo": {
        "label": "Key Combo",
        "category": "hid",
        "params": [
            {"key": "modifiers", "label": "MODIFIERS (comma-sep)", "type": "text", "required": True},
            {"key": "key", "label": "KEY", "type": "text", "required": True},
        ],
    },
    "hid_mouse_move": {
        "label": "Mouse Move",
        "category": "hid",
        "params": [
            {"key": "x", "label": "X", "type": "number", "default": 0},
            {"key": "y", "label": "Y", "type": "number", "default": 0},
            {"key": "relative", "label": "RELATIVE", "type": "checkbox", "default": True},
        ],
    },
    "hid_mouse_click": {
        "label": "Mouse Click",
        "category": "hid",
        "params": [
            {"key": "button", "label": "BUTTON", "type": "select",
             "options": ["left", "right", "middle"], "default": "left"},
            {"key": "count", "label": "CLICKS", "type": "number", "default": 1},
        ],
    },
    "hid_scroll": {
        "label": "Scroll",
        "category": "hid",
        "params": [
            {"key": "amount", "label": "AMOUNT", "type": "number", "default": 3},
        ],
    },
    "hid_paste_from_sd": {
        "label": "Paste from SD Card",
        "category": "hid",
        "params": [
            {"key": "filename", "label": "FILENAME", "type": "text", "required": True},
        ],
    },
    "hid_upload_from_sd": {
        "label": "Upload File from SD Card",
        "category": "hid",
        "params": [
            {"key": "filename", "label": "SOURCE (SD path)", "type": "text", "required": True},
            {"key": "destination", "label": "DESTINATION (host path)", "type": "text", "required": True},
        ],
    },
    "hid_download_file": {
        "label": "Download File from Remote",
        "category": "hid",
        "params": [
            {"key": "url", "label": "URL", "type": "text", "required": True},
            {"key": "local_path", "label": "SAVE TO (host path)", "type": "text", "required": True},
        ],
    },
    # ------------------------------------------------------------------
    # Serial
    # ------------------------------------------------------------------
    "serial_send_string": {
        "label": "Send String",
        "category": "serial",
        "params": [
            {"key": "text", "label": "STRING", "type": "text", "required": True},
            {"key": "device", "label": "DEVICE", "type": "text", "default": "/dev/ttyGS0"},
        ],
    },
    "serial_send_sequence": {
        "label": "Send Sequence",
        "category": "serial",
        "params": [
            {"key": "sequence", "label": "SEQUENCE (JSON array or comma-sep hex)", "type": "textarea", "required": True},
            {"key": "device", "label": "DEVICE", "type": "text", "default": "/dev/ttyGS0"},
        ],
    },
    "serial_wait_response": {
        "label": "Wait for Response",
        "category": "serial",
        "params": [
            {"key": "match", "label": "MATCH STRING", "type": "text", "required": True},
            {"key": "timeout_ms", "label": "TIMEOUT (ms)", "type": "number", "default": 5000},
            {"key": "device", "label": "DEVICE", "type": "text", "default": "/dev/ttyGS0"},
        ],
    },
    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    "net_provide_dhcp": {
        "label": "Provide DHCP",
        "category": "network",
        "params": [
            {"key": "interface", "label": "INTERFACE", "type": "text", "default": "usb0"},
            {"key": "subnet", "label": "SUBNET", "type": "text", "default": "192.168.7.0/24"},
            {"key": "gateway", "label": "GATEWAY IP", "type": "text", "default": "192.168.7.1"},
            {"key": "range_start", "label": "RANGE START", "type": "text", "default": "192.168.7.2"},
            {"key": "range_end", "label": "RANGE END", "type": "text", "default": "192.168.7.10"},
        ],
    },
    "net_provide_dns": {
        "label": "Provide DNS",
        "category": "network",
        "params": [
            {"key": "interface", "label": "INTERFACE", "type": "text", "default": "usb0"},
            {"key": "domain", "label": "DOMAIN", "type": "text", "required": True},
            {"key": "response", "label": "RESPONSE IP", "type": "text", "required": True},
        ],
    },
    "net_static_response": {
        "label": "Static HTTP Response",
        "category": "network",
        "params": [
            {"key": "interface", "label": "INTERFACE", "type": "text", "default": "usb0"},
            {"key": "port", "label": "PORT", "type": "number", "default": 80},
            {"key": "body", "label": "RESPONSE BODY", "type": "textarea", "default": "OK"},
        ],
    },
    "net_log_traffic": {
        "label": "Log Traffic Metadata",
        "category": "network",
        "params": [
            {"key": "interface", "label": "INTERFACE", "type": "text", "default": "usb0"},
            {"key": "log_path", "label": "LOG PATH", "type": "text", "default": "/userdata/captures/traffic.log"},
        ],
    },
    "net_respond_ping": {
        "label": "Respond to Ping",
        "category": "network",
        "params": [
            {"key": "interface", "label": "INTERFACE", "type": "text", "default": "usb0"},
        ],
    },
    # ------------------------------------------------------------------
    # Gadget Profile
    # ------------------------------------------------------------------
    "gadget_switch_hid": {
        "label": "Switch to HID Profile",
        "category": "gadget",
        "params": [
            {"key": "mouse", "label": "INCLUDE MOUSE", "type": "checkbox", "default": True},
        ],
    },
    "gadget_switch_serial": {
        "label": "Switch to Serial Profile",
        "category": "gadget",
        "params": [],
    },
    "gadget_switch_ethernet": {
        "label": "Switch to Ethernet Profile",
        "category": "gadget",
        "params": [
            {"key": "mode", "label": "MODE (rndis/ecm/ncm)", "type": "select",
             "options": ["rndis", "ecm", "ncm"], "default": "rndis"},
        ],
    },
    "gadget_switch_composite": {
        "label": "Switch to Composite Profile",
        "category": "gadget",
        "params": [
            {"key": "functions", "label": "FUNCTIONS (comma-sep: hid,serial,ethernet)", "type": "text",
             "default": "hid,serial"},
        ],
    },
    "gadget_load_from_sd": {
        "label": "Load Profile from SD Card",
        "category": "gadget",
        "params": [
            {"key": "filename", "label": "PROFILE FILENAME", "type": "text", "required": True},
        ],
    },
    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------
    "delay": {
        "label": "Delay",
        "category": "timing",
        "params": [
            {"key": "ms", "label": "DURATION (ms)", "type": "number", "default": 500, "required": True},
        ],
    },
    "wait_event": {
        "label": "Wait for Event",
        "category": "timing",
        "params": [
            {"key": "event", "label": "EVENT", "type": "select",
             "options": ["usb_hid", "usb_serial", "usb_rndis", "serial_open", "network_up"],
             "default": "usb_hid"},
            {"key": "timeout_ms", "label": "TIMEOUT (ms)", "type": "number", "default": 10000},
        ],
    },
}

# ---------------------------------------------------------------------------
# Composite gadget function profiles
# ---------------------------------------------------------------------------

COMPOSITE_PROFILES: Dict[str, Dict[str, Any]] = {
    "hid_serial": {
        "label": "HID + Serial",
        "functions": ["hid", "serial"],
    },
    "hid_ethernet": {
        "label": "HID + Ethernet",
        "functions": ["hid", "ethernet"],
    },
    "serial_ethernet": {
        "label": "Serial + Ethernet",
        "functions": ["serial", "ethernet"],
    },
    "hid_serial_ethernet": {
        "label": "HID + Serial + Ethernet",
        "functions": ["hid", "serial", "ethernet"],
    },
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VALID_BLOCK_TYPES = set(BLOCK_TYPES.keys())


def validate_block(block: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    btype = block.get("type")
    if not btype:
        errors.append("block is missing 'type'")
        return errors
    if btype not in _VALID_BLOCK_TYPES:
        errors.append(f"unknown block type: '{btype}'")
        return errors
    schema = BLOCK_TYPES[btype]
    params = block.get("params", {})
    for pdef in schema.get("params", []):
        if pdef.get("required") and pdef["key"] not in params:
            errors.append(f"missing required param '{pdef['key']}' for block type '{btype}'")
    return errors


def validate_workflow(workflow: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(workflow, dict):
        return ["workflow must be a JSON object"]
    if "blocks" not in workflow:
        errors.append("workflow is missing 'blocks' array")
        return errors
    if not isinstance(workflow["blocks"], list):
        errors.append("'blocks' must be an array")
        return errors
    # Validate structural balance: loop / if blocks
    depth_loop = 0
    depth_if = 0
    for i, block in enumerate(workflow["blocks"]):
        errs = validate_block(block)
        for e in errs:
            errors.append(f"block[{i}]: {e}")
        t = block.get("type", "")
        if t == "loop_n":
            depth_loop += 1
        elif t == "end_loop":
            depth_loop -= 1
            if depth_loop < 0:
                errors.append(f"block[{i}]: 'end_loop' without matching 'loop_n'")
                depth_loop = 0
        elif t == "if_os":
            depth_if += 1
        elif t == "end_if":
            depth_if -= 1
            if depth_if < 0:
                errors.append(f"block[{i}]: 'end_if' without matching 'if_os'")
                depth_if = 0
    if depth_loop > 0:
        errors.append(f"{depth_loop} unclosed 'loop_n' block(s)")
    if depth_if > 0:
        errors.append(f"{depth_if} unclosed 'if_os' block(s)")
    return errors


def schema_manifest() -> Dict[str, Any]:
    """Return a serialisable description of the full schema for the UI."""
    return {
        "version": SCHEMA_VERSION,
        "trigger_types": TRIGGER_TYPES,
        "block_categories": BLOCK_CATEGORIES,
        "block_types": BLOCK_TYPES,
        "composite_profiles": COMPOSITE_PROFILES,
        "os_options": OS_OPTIONS,
    }
