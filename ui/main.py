"""
Onikiri Mk.I — UI Entry Point (Kivy application)

Design rationale for Kivy over a web UI:
  - Runs directly on KMS/DRM framebuffer; no X11, no Wayland, no browser engine.
  - SDL2+EGL backend renders via OpenGL ES 2.0 — compatible with Mali/PowerVR.
  - Saves ~400–600 ms of boot time by eliminating a display server startup.
  - Touch input via evdev is native to Kivy.
  - Python → zero FFI overhead when calling supervisor IPC.

The app connects to the supervisor over a Unix socket and refreshes module
state every 2 seconds. All commands are dispatched as JSON IPC messages.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from pathlib import Path

# Kivy environment — must be set before importing kivy
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_WINDOW", "sdl2")
os.environ.setdefault("SDL_VIDEODRIVER", os.environ.get("SDL_VIDEODRIVER", "kmsdrm"))

from kivy.app import App                             # noqa: E402
from kivy.clock import Clock                          # noqa: E402
from kivy.config import Config                        # noqa: E402
from kivy.core.window import Window                   # noqa: E402
from kivy.lang import Builder                         # noqa: E402
from kivy.uix.boxlayout import BoxLayout              # noqa: E402
from kivy.uix.floatlayout import FloatLayout          # noqa: E402

from ui import theme                                  # noqa: E402
from ui.widgets.module_panel import ModulePanel       # noqa: E402
from ui.widgets.overlay import AdvancedOverlay        # noqa: E402
from ui.widgets.status_bar import OnikiriStatusBar    # noqa: E402

# ── Kivy configuration — fullscreen, hide cursor ──────────────────────────────
Config.set("graphics", "fullscreen", "auto")
Config.set("graphics", "show_cursor", "0")
Config.set("graphics", "borderless", "1")
Config.set("input", "mouse", "mouse,disable_multitouch")

# ── Load KV layout ────────────────────────────────────────────────────────────
_KV_PATH = Path(__file__).parent / "app.kv"
Builder.load_file(str(_KV_PATH))

SOCKET_PATH = "/run/onikiri/supervisor.sock"
STATUS_POLL_INTERVAL = 2.0   # seconds


# ─────────────────────────────────────────────────────────────────────────────
# IPC client — runs in a background thread
# ─────────────────────────────────────────────────────────────────────────────

class IPCClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0

    def send(self, cmd: str, args: dict | None = None) -> dict | None:
        with self._lock:
            return self._send_raw(cmd, args or {})

    def _send_raw(self, cmd: str, args: dict) -> dict | None:
        self._seq += 1
        req = json.dumps({"id": str(self._seq), "cmd": cmd, "args": args})
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect(SOCKET_PATH)
            sock.sendall(req.encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            sock.close()
            return json.loads(data.decode())
        except (OSError, json.JSONDecodeError):
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Root widget
# ─────────────────────────────────────────────────────────────────────────────

class OnikiriRoot(BoxLayout):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────

class OnikiriApp(App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ipc = IPCClient()
        self._panels: dict[str, ModulePanel] = {}
        self._root_widget: OnikiriRoot | None = None

    def build(self) -> FloatLayout:
        self.title = "Onikiri Mk.I"
        Window.clearcolor = theme.BG_COLOR

        # Outer float layout allows overlay to sit above the grid
        outer = FloatLayout()
        root = OnikiriRoot()
        self._root_widget = root
        outer.add_widget(root)

        self._build_panels(root)
        Clock.schedule_interval(self._poll_status, STATUS_POLL_INTERVAL)
        Clock.schedule_once(self._initial_poll, 0.5)
        return outer

    def _build_panels(self, root: OnikiriRoot) -> None:
        grid = root.ids.get("panel_grid")
        if grid is None:
            return
        for spec in theme.PANELS:
            panel = ModulePanel(
                label=spec["label"],
                module_id=spec["module"],
            )
            panel.on_tap = self._on_panel_tap
            panel.on_long_press = self._on_panel_long_press
            grid.add_widget(panel)
            self._panels[spec["module"]] = panel

    # ── Interaction callbacks ─────────────────────────────────────────────────

    def _on_panel_tap(self, panel: ModulePanel) -> None:
        self._update_status_bar(f"{panel.label_text}: requesting status")
        threading.Thread(
            target=self._fetch_module_status,
            args=(panel.module_id,),
            daemon=True,
        ).start()

    def _on_panel_long_press(self, panel: ModulePanel) -> None:
        # Fetch module info and show overlay
        threading.Thread(
            target=self._show_overlay_for,
            args=(panel,),
            daemon=True,
        ).start()

    def _show_overlay_for(self, panel: ModulePanel) -> None:
        response = self._ipc.send("module_status", {"module": panel.module_id})
        if response and response.get("status") == "ok":
            commands = response["result"].get("commands", {})
        else:
            commands = {}

        def _on_main(_dt) -> None:
            overlay = AdvancedOverlay(
                module_label=panel.label_text,
                commands=commands,
                on_execute=lambda cmd: self._execute_command(panel.module_id, cmd),
                size_hint=(0.85, 0.85),
                pos_hint={"center_x": 0.5, "center_y": 0.5},
            )
            outer = self._root_widget.parent
            if outer:
                outer.add_widget(overlay)

        Clock.schedule_once(_on_main, 0)

    # ── Command execution ──────────────────────────────────────────────────────

    def _execute_command(self, module_id: str, command: str) -> None:
        panel = self._panels.get(module_id)
        if panel:
            Clock.schedule_once(lambda _: panel.set_state("running", command.upper()), 0)
        threading.Thread(
            target=self._run_and_update,
            args=(module_id, command),
            daemon=True,
        ).start()

    def _run_and_update(self, module_id: str, command: str) -> None:
        response = self._ipc.send("execute", {
            "module": module_id,
            "command": command,
            "params": {},
        })
        panel = self._panels.get(module_id)
        if panel is None:
            return

        if response and response.get("status") == "ok":
            job_id = response["result"].get("job_id")
            # Wait for job completion (simple poll)
            self._wait_job(panel, job_id)
        else:
            Clock.schedule_once(
                lambda _: panel.set_state("error", "IPC ERR"), 0
            )

    def _wait_job(self, panel: ModulePanel, job_id: str) -> None:
        for _ in range(60):
            time.sleep(1.0)
            resp = self._ipc.send("job_status", {"job_id": job_id})
            if resp and resp.get("status") == "ok":
                job = resp["result"]
                status = job.get("status", "")
                if status == "done":
                    Clock.schedule_once(lambda _: panel.set_state("active", "DONE"), 0)
                    return
                if status in ("error", "cancelled"):
                    Clock.schedule_once(
                        lambda _: panel.set_state("error", status.upper()), 0
                    )
                    return
        Clock.schedule_once(lambda _: panel.set_state("idle"), 0)

    # ── Status polling ─────────────────────────────────────────────────────────

    def _initial_poll(self, _dt) -> None:
        threading.Thread(target=self._poll_all, daemon=True).start()

    def _poll_status(self, _dt) -> None:
        threading.Thread(target=self._poll_all, daemon=True).start()

    def _poll_all(self) -> None:
        response = self._ipc.send("list_modules")
        if response and response.get("status") == "ok":
            modules = response["result"].get("modules", [])
            for mod in modules:
                panel = self._panels.get(mod["name"])
                if panel:
                    state = mod.get("state", "idle")
                    Clock.schedule_once(
                        lambda _, p=panel, s=state: p.set_state(s), 0
                    )

    def _fetch_module_status(self, module_id: str) -> None:
        response = self._ipc.send("module_status", {"module": module_id})
        panel = self._panels.get(module_id)
        if panel and response and response.get("status") == "ok":
            state = response["result"].get("state", "idle")
            Clock.schedule_once(lambda _, p=panel, s=state: p.set_state(s), 0)

    def _update_status_bar(self, msg: str) -> None:
        def _update(_dt) -> None:
            bar = self._root_widget.ids.get("status_bar") if self._root_widget else None
            if bar:
                bar.set_status(msg)
        Clock.schedule_once(_update, 0)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    OnikiriApp().run()
