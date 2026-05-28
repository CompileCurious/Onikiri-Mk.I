"""
Onikiri Mk.I — HID payload parser.

Converts DuckyScript (.duck), raw text (.txt), or .payload files into
a list of HID block dicts that can be stored in a BlockStore.

DuckyScript grammar supported:
  REM <comment>
  DELAY <ms>
  STRING <text>
  ENTER / RETURN
  TAB, ESCAPE, ESC, SPACE, BACKSPACE, DELETE
  UP, DOWN, LEFT, RIGHT, HOME, END, PAGE_UP, PAGE_DOWN
  INSERT, CAPSLOCK, F1..F12
  GUI <key> / WINDOWS <key>
  CTRL <key>
  ALT <key>
  SHIFT <key>
  CTRL-ALT <key>
  CTRL-SHIFT <key>
  ALT-SHIFT <key>
  GUI-SHIFT <key>
  REPEAT <n>   (repeats the immediately preceding block n-1 additional times)
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from onikiri.hid.schema import MODIFIER_BITS, NAMED_KEYS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _delay_block(ms: int) -> Dict[str, Any]:
    return {"id": _new_id(), "type": "delay", "enabled": True, "params": {"ms": ms}}


def _type_block(text: str) -> Dict[str, Any]:
    return {"id": _new_id(), "type": "type_text", "enabled": True,
            "params": {"text": text, "delay_ms": 20}}


def _press_block(key: str) -> Dict[str, Any]:
    return {"id": _new_id(), "type": "press_key", "enabled": True, "params": {"key": key}}


def _combo_block(modifiers: List[str], key: str) -> Dict[str, Any]:
    return {
        "id": _new_id(),
        "type": "key_combo",
        "enabled": True,
        "params": {"modifiers": modifiers, "key": key},
    }


# Map single-word DuckyScript tokens to named keys
_TOKEN_TO_KEY: Dict[str, str] = {
    "ENTER": "ENTER", "RETURN": "ENTER",
    "TAB": "TAB",
    "ESCAPE": "ESCAPE", "ESC": "ESCAPE",
    "SPACE": "SPACE",
    "BACKSPACE": "BACKSPACE",
    "DELETE": "DELETE",
    "UP": "UP", "ARROW_UP": "UP",
    "DOWN": "DOWN", "ARROW_DOWN": "DOWN",
    "LEFT": "LEFT", "ARROW_LEFT": "LEFT",
    "RIGHT": "RIGHT", "ARROW_RIGHT": "RIGHT",
    "HOME": "HOME",
    "END": "END",
    "PAGE_UP": "PAGE_UP", "PAGEUP": "PAGE_UP",
    "PAGE_DOWN": "PAGE_DOWN", "PAGEDOWN": "PAGE_DOWN",
    "INSERT": "INSERT",
    "CAPSLOCK": "CAPS_LOCK", "CAPS_LOCK": "CAPS_LOCK",
    "NUMLOCK": "NUMLOCK",
    "SCROLL_LOCK": "SCROLL_LOCK",
    "PRINT_SCREEN": "PRINT_SCREEN",
    "PAUSE": "PAUSE",
    "APP": "APP", "MENU": "MENU",
    **{f"F{n}": f"F{n}" for n in range(1, 13)},
}

# Map prefix tokens to modifier lists
_PREFIX_MODIFIERS: Dict[str, List[str]] = {
    "GUI":         ["GUI"],
    "WINDOWS":     ["GUI"],
    "CTRL":        ["CTRL"],
    "ALT":         ["ALT"],
    "SHIFT":       ["SHIFT"],
    "CTRL-ALT":    ["CTRL", "ALT"],
    "CTRL-SHIFT":  ["CTRL", "SHIFT"],
    "ALT-SHIFT":   ["ALT", "SHIFT"],
    "GUI-SHIFT":   ["GUI", "SHIFT"],
    "GUI-CTRL":    ["GUI", "CTRL"],
    "CTRL-ALT-SHIFT": ["CTRL", "ALT", "SHIFT"],
}


def _parse_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single DuckyScript line into a block dict, or None to skip."""
    line = line.strip()
    if not line or line.startswith("REM") or line.startswith("//") or line.startswith("#"):
        return None

    upper = line.upper()

    # DELAY
    if upper.startswith("DELAY "):
        try:
            ms = int(line.split(None, 1)[1].strip())
            return _delay_block(ms)
        except (ValueError, IndexError):
            return _delay_block(500)

    # STRING
    if upper.startswith("STRING "):
        text = line[7:]  # preserve original case
        return _type_block(text)

    # STRINGLN (STRING + ENTER)
    if upper.startswith("STRINGLN "):
        text = line[9:] + "\n"
        return _type_block(text)

    # Single-token named keys
    token = upper.split()[0]
    if token in _TOKEN_TO_KEY:
        return _press_block(_TOKEN_TO_KEY[token])

    # Modifier prefix + key
    # Try longest prefix first
    for prefix in sorted(_PREFIX_MODIFIERS.keys(), key=len, reverse=True):
        if upper.startswith(prefix + " "):
            key_part = line[len(prefix):].strip().upper()
            # Key part might be a named key or single letter
            resolved_key = _TOKEN_TO_KEY.get(key_part, key_part)
            return _combo_block(_PREFIX_MODIFIERS[prefix], resolved_key)

    return None


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------

def parse_duckyscript(content: str) -> List[Dict[str, Any]]:
    """Parse DuckyScript content into a list of HID block dicts."""
    blocks: List[Dict[str, Any]] = []
    for line in content.splitlines():
        upper = line.strip().upper()

        # REPEAT: duplicate the last block N times
        if upper.startswith("REPEAT "):
            try:
                n = int(line.split(None, 1)[1].strip())
            except (ValueError, IndexError):
                continue
            if blocks:
                last = dict(blocks[-1])
                for _ in range(n - 1):
                    dup = dict(last, id=_new_id())
                    blocks.append(dup)
            continue

        block = _parse_line(line)
        if block is not None:
            blocks.append(block)

    return blocks


def parse_raw_text(content: str) -> List[Dict[str, Any]]:
    """
    Treat a raw text file as a sequence to type verbatim, with each line
    followed by ENTER. Produces minimal block list.
    """
    blocks: List[Dict[str, Any]] = []
    for line in content.splitlines():
        if line:
            blocks.append(_type_block(line + "\n"))
        else:
            blocks.append(_press_block("ENTER"))
    return blocks


def parse_payload_file(filename: str, content: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Auto-detect format from extension and parse accordingly.
    Returns (format_name, blocks).
    """
    lower = filename.lower()
    if lower.endswith(".duck") or lower.endswith(".ducky"):
        return "duckyscript", parse_duckyscript(content)
    if lower.endswith(".payload"):
        # .payload files commonly use DuckyScript
        return "duckyscript", parse_duckyscript(content)
    # .txt or anything else: raw type
    return "raw_text", parse_raw_text(content)
