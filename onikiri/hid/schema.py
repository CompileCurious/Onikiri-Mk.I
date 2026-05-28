from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Modifier bitmasks (USB HID spec, byte 0 of keyboard report)
# ---------------------------------------------------------------------------

MODIFIER_BITS: Dict[str, int] = {
    "CTRL":   0x01,
    "LCTRL":  0x01,
    "SHIFT":  0x02,
    "LSHIFT": 0x02,
    "ALT":    0x04,
    "LALT":   0x04,
    "GUI":    0x08,
    "WIN":    0x08,
    "META":   0x08,
    "LGUI":   0x08,
    "RCTRL":  0x10,
    "RSHIFT": 0x20,
    "RALT":   0x40,
    "ALTGR":  0x40,
    "RGUI":   0x80,
    "RWIN":   0x80,
}

# ---------------------------------------------------------------------------
# USB HID keyboard scancodes (US layout)
# ---------------------------------------------------------------------------

NAMED_KEYS: Dict[str, int] = {
    # Letters
    "A": 0x04, "B": 0x05, "C": 0x06, "D": 0x07, "E": 0x08,
    "F": 0x09, "G": 0x0A, "H": 0x0B, "I": 0x0C, "J": 0x0D,
    "K": 0x0E, "L": 0x0F, "M": 0x10, "N": 0x11, "O": 0x12,
    "P": 0x13, "Q": 0x14, "R": 0x15, "S": 0x16, "T": 0x17,
    "U": 0x18, "V": 0x19, "W": 0x1A, "X": 0x1B, "Y": 0x1C,
    "Z": 0x1D,
    # Numbers
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    # Control
    "ENTER":     0x28, "RETURN":    0x28,
    "ESCAPE":    0x29, "ESC":       0x29,
    "BACKSPACE": 0x2A, "DELETE":    0x4C,
    "TAB":       0x2B,
    "SPACE":     0x2C,
    "CAPS_LOCK": 0x39, "CAPSLOCK":  0x39,
    # Punctuation (US)
    "MINUS":     0x2D,
    "EQUAL":     0x2E,
    "LEFTBRACE": 0x2F,
    "RIGHTBRACE":0x30,
    "BACKSLASH": 0x31,
    "SEMICOLON": 0x33,
    "APOSTROPHE":0x34,
    "GRAVE":     0x35,
    "COMMA":     0x36,
    "DOT":       0x37,
    "SLASH":     0x38,
    # Function keys
    "F1":  0x3A, "F2":  0x3B, "F3":  0x3C, "F4":  0x3D,
    "F5":  0x3E, "F6":  0x3F, "F7":  0x40, "F8":  0x41,
    "F9":  0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    # Navigation
    "INSERT":    0x49,
    "HOME":      0x4A,
    "PAGE_UP":   0x4B, "PAGEUP":   0x4B,
    "END":       0x4D,
    "PAGE_DOWN": 0x4E, "PAGEDOWN": 0x4E,
    "RIGHT":     0x4F, "ARROW_RIGHT": 0x4F,
    "LEFT":      0x50, "ARROW_LEFT":  0x50,
    "DOWN":      0x51, "ARROW_DOWN":  0x51,
    "UP":        0x52, "ARROW_UP":    0x52,
    # Numpad
    "NUMLOCK":   0x53,
    "KP_SLASH":  0x54,
    "KP_STAR":   0x55,
    "KP_MINUS":  0x56,
    "KP_PLUS":   0x57,
    "KP_ENTER":  0x58,
    "KP_1": 0x59, "KP_2": 0x5A, "KP_3": 0x5B,
    "KP_4": 0x5C, "KP_5": 0x5D, "KP_6": 0x5E,
    "KP_7": 0x5F, "KP_8": 0x60, "KP_9": 0x61,
    "KP_0": 0x62, "KP_DOT": 0x63,
    # Print / scroll / pause
    "PRINT_SCREEN": 0x46,
    "SCROLL_LOCK":  0x47,
    "PAUSE":        0x48,
    # Application key
    "APP":  0x65,
    "MENU": 0x76,
}

# Map US printable characters → (modifier, scancode)
_CHAR_TO_HID: Dict[str, Tuple[int, int]] = {}

# Unshifted characters
_UNSHIFTED = {
    "a": "A", "b": "B", "c": "C", "d": "D", "e": "E",
    "f": "F", "g": "G", "h": "H", "i": "I", "j": "J",
    "k": "K", "l": "L", "m": "M", "n": "N", "o": "O",
    "p": "P", "q": "Q", "r": "R", "s": "S", "t": "T",
    "u": "U", "v": "V", "w": "W", "x": "X", "y": "Y",
    "z": "Z",
    "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
    "6": "6", "7": "7", "8": "8", "9": "9", "0": "0",
    "\n": "ENTER", "\r": "ENTER", "\t": "TAB", " ": "SPACE",
    "-": "MINUS", "=": "EQUAL", "[": "LEFTBRACE",
    "]": "RIGHTBRACE", "\\": "BACKSLASH", ";": "SEMICOLON",
    "'": "APOSTROPHE", "`": "GRAVE", ",": "COMMA",
    ".": "DOT", "/": "SLASH",
}

# Shifted characters
_SHIFTED = {
    "A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
    "F": "F", "G": "G", "H": "H", "I": "I", "J": "J",
    "K": "K", "L": "L", "M": "M", "N": "N", "O": "O",
    "P": "P", "Q": "Q", "R": "R", "S": "S", "T": "T",
    "U": "U", "V": "V", "W": "W", "X": "X", "Y": "Y",
    "Z": "Z",
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "MINUS", "+": "EQUAL", "{": "LEFTBRACE",
    "}": "RIGHTBRACE", "|": "BACKSLASH", ":": "SEMICOLON",
    '"': "APOSTROPHE", "~": "GRAVE", "<": "COMMA",
    ">": "DOT", "?": "SLASH",
}

for _ch, _key in _UNSHIFTED.items():
    if _key in NAMED_KEYS:
        _CHAR_TO_HID[_ch] = (0x00, NAMED_KEYS[_key])

for _ch, _key in _SHIFTED.items():
    if _key in NAMED_KEYS:
        _CHAR_TO_HID[_ch] = (0x02, NAMED_KEYS[_key])  # LSHIFT


def char_to_hid(ch: str) -> Tuple[int, int]:
    """Return (modifier, scancode) for a printable character, or (0, 0) if unsupported."""
    return _CHAR_TO_HID.get(ch, (0, 0))


# ---------------------------------------------------------------------------
# Block type definitions
# ---------------------------------------------------------------------------

BLOCK_TYPES: Dict[str, Dict[str, Any]] = {
    # Keyboard
    "type_text": {
        "label": "TYPE TEXT",
        "category": "keyboard",
        "params": [
            {"id": "text",      "label": "TEXT",         "type": "text"},
            {"id": "delay_ms",  "label": "INTER-KEY MS", "type": "number", "default": 20},
        ],
    },
    "press_key": {
        "label": "PRESS KEY",
        "category": "keyboard",
        "params": [
            {"id": "key",       "label": "KEY",          "type": "key_select"},
        ],
    },
    "hold_key": {
        "label": "HOLD KEY",
        "category": "keyboard",
        "params": [
            {"id": "key",       "label": "KEY",          "type": "key_select"},
        ],
    },
    "release_key": {
        "label": "RELEASE KEY",
        "category": "keyboard",
        "params": [
            {"id": "key",       "label": "KEY",          "type": "key_select"},
        ],
    },
    "key_combo": {
        "label": "KEY COMBO",
        "category": "keyboard",
        "params": [
            {"id": "modifiers", "label": "MODIFIERS",    "type": "modifier_multi"},
            {"id": "key",       "label": "KEY",          "type": "key_select"},
        ],
    },
    # Mouse
    "mouse_move": {
        "label": "MOUSE MOVE",
        "category": "mouse",
        "params": [
            {"id": "x",         "label": "X (REL)",      "type": "number", "default": 0},
            {"id": "y",         "label": "Y (REL)",      "type": "number", "default": 0},
        ],
    },
    "mouse_click": {
        "label": "MOUSE CLICK",
        "category": "mouse",
        "params": [
            {"id": "button",    "label": "BUTTON",       "type": "select",
             "options": ["left", "right", "middle"]},
        ],
    },
    "mouse_scroll": {
        "label": "MOUSE SCROLL",
        "category": "mouse",
        "params": [
            {"id": "direction", "label": "DIRECTION",    "type": "select",
             "options": ["up", "down"]},
            {"id": "amount",    "label": "CLICKS",       "type": "number", "default": 3},
        ],
    },
    # Timing
    "delay": {
        "label": "DELAY",
        "category": "timing",
        "params": [
            {"id": "ms",        "label": "MILLISECONDS", "type": "number", "default": 500},
        ],
    },
    "wait_window": {
        "label": "WAIT (WINDOW HINT)",
        "category": "timing",
        "params": [
            {"id": "title",       "label": "WINDOW TITLE HINT", "type": "text"},
            {"id": "timeout_ms",  "label": "TIMEOUT MS",        "type": "number", "default": 2000},
        ],
    },
    # Flow
    "loop_start": {
        "label": "LOOP START",
        "category": "flow",
        "params": [
            {"id": "count",     "label": "REPEAT COUNT", "type": "number", "default": 3},
        ],
    },
    "loop_end": {
        "label": "LOOP END",
        "category": "flow",
        "params": [],
    },
    "if_condition": {
        "label": "IF",
        "category": "flow",
        "params": [
            {"id": "field",     "label": "FIELD",        "type": "select",
             "options": ["os_type", "window_title"]},
            {"id": "operator",  "label": "OPERATOR",     "type": "select",
             "options": ["equals", "contains"]},
            {"id": "value",     "label": "VALUE",        "type": "text"},
        ],
    },
    "else_block": {
        "label": "ELSE",
        "category": "flow",
        "params": [],
    },
    "endif": {
        "label": "END IF",
        "category": "flow",
        "params": [],
    },
    # System shortcuts
    "open_run": {
        "label": "OPEN RUN DIALOG",
        "category": "system",
        "params": [
            {"id": "target_os", "label": "TARGET OS",   "type": "select",
             "options": ["windows", "linux", "macos"]},
        ],
    },
    "open_terminal": {
        "label": "OPEN TERMINAL",
        "category": "system",
        "params": [
            {"id": "target_os", "label": "TARGET OS",   "type": "select",
             "options": ["windows", "linux", "macos"]},
        ],
    },
    "paste_clipboard": {
        "label": "PASTE CLIPBOARD",
        "category": "system",
        "params": [
            {"id": "target_os", "label": "TARGET OS",   "type": "select",
             "options": ["windows", "linux", "macos"]},
        ],
    },
}

BLOCK_CATEGORIES: Dict[str, str] = {
    "keyboard": "KEYBOARD",
    "mouse":    "MOUSE",
    "timing":   "TIMING",
    "flow":     "FLOW",
    "system":   "SYSTEM",
}

# ---------------------------------------------------------------------------
# USB device profiles
# ---------------------------------------------------------------------------

USB_DEVICE_PROFILES: Dict[str, Dict[str, str]] = {
    "generic_keyboard": {
        "label":        "Generic USB Keyboard",
        "vid":          "0x1d6b",
        "pid":          "0x0104",
        "manufacturer": "Generic",
        "product":      "USB Keyboard",
        "serial":       "HID001",
    },
    "apple_keyboard": {
        "label":        "Apple USB Keyboard",
        "vid":          "0x05ac",
        "pid":          "0x020b",
        "manufacturer": "Apple Inc.",
        "product":      "Apple Keyboard",
        "serial":       "AK001",
    },
    "logitech_k280e": {
        "label":        "Logitech K280e",
        "vid":          "0x046d",
        "pid":          "0xc31c",
        "manufacturer": "Logitech",
        "product":      "USB Keyboard K280e",
        "serial":       "LK280",
    },
    "dell_kb216": {
        "label":        "Dell KB216",
        "vid":          "0x413c",
        "pid":          "0x2113",
        "manufacturer": "Dell",
        "product":      "Dell USB Keyboard",
        "serial":       "DL001",
    },
    "microsoft_400": {
        "label":        "Microsoft 400",
        "vid":          "0x045e",
        "pid":          "0x07b2",
        "manufacturer": "Microsoft",
        "product":      "Microsoft USB Keyboard",
        "serial":       "MS400",
    },
    "samsung_keyboard": {
        "label":        "Samsung USB Keyboard",
        "vid":          "0x04e8",
        "pid":          "0x7021",
        "manufacturer": "Samsung",
        "product":      "Samsung USB Keyboard",
        "serial":       "SAM001",
    },
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_PARAMS: Dict[str, List[str]] = {
    "type_text":     ["text"],
    "press_key":     ["key"],
    "hold_key":      ["key"],
    "release_key":   ["key"],
    "key_combo":     ["key"],
    "mouse_move":    [],
    "mouse_click":   ["button"],
    "mouse_scroll":  ["direction"],
    "delay":         ["ms"],
    "wait_window":   ["timeout_ms"],
    "loop_start":    ["count"],
    "loop_end":      [],
    "if_condition":  ["field", "value"],
    "else_block":    [],
    "endif":         [],
    "open_run":      ["target_os"],
    "open_terminal": ["target_os"],
    "paste_clipboard": [],
}


def validate_block(block: Dict[str, Any]) -> List[str]:
    """Return a list of validation errors. Empty list means the block is valid."""
    errors: List[str] = []
    if not block.get("id"):
        errors.append("block missing 'id'")
    btype = block.get("type")
    if btype not in BLOCK_TYPES:
        errors.append(f"unknown block type: {btype!r}")
        return errors
    params = block.get("params", {})
    for req in REQUIRED_PARAMS.get(btype, []):
        if req not in params:
            errors.append(f"block '{btype}' missing required param '{req}'")
    return errors
