"""
Onikiri Mk.I — Module Panel Widget
A single rectangular panel in the 3×2 HMI grid.

States:
  idle    — dim border, grey strip
  active  — red border, red strip, slow pulse
  running — bright red, animated strip
  error   — white/red strobe
"""

from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.properties import (
    ColorProperty, ListProperty, NumericProperty, StringProperty,
)
from kivy.uix.boxlayout import BoxLayout

from ui import theme


class ModulePanel(BoxLayout):
    # ── Kivy properties ───────────────────────────────────────────────────────
    label_text   = StringProperty("")
    module_id    = StringProperty("")
    status_text  = StringProperty("IDLE")

    panel_fill   = ColorProperty(theme.PANEL_BG)
    border_color = ColorProperty(theme.BORDER_COLOR)
    flash_color  = ColorProperty((0, 0, 0, 0))
    strip_color  = ColorProperty(theme.STATUS_IDLE)
    label_color  = ColorProperty(theme.TEXT_COLOR)
    icon_color   = ColorProperty(theme.BORDER_COLOR)

    # Internal state
    _state       = StringProperty("idle")
    _long_press_threshold = 0.65   # seconds

    def __init__(self, label: str, module_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label_text = label
        self.module_id = module_id
        self._touch_time: float = 0.0
        self._pulse_event = None
        self._strobe_event = None
        self._strobe_state = False
        # Callback set by parent app to open overlay
        self.on_long_press = None
        # Callback set by parent app to execute default command
        self.on_tap = None

    # ── Touch handling ────────────────────────────────────────────────────────

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._touch_time = touch.time_start
        touch.grab(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        elapsed = touch.time_end - self._touch_time
        if elapsed >= self._long_press_threshold:
            self._trigger_long_press()
        else:
            self._trigger_tap()
        return True

    # ── Tap ───────────────────────────────────────────────────────────────────

    def _trigger_tap(self) -> None:
        # Brief red flash
        self.flash_color = theme.FLASH_COLOR
        Clock.schedule_once(self._clear_flash, theme.FLASH_DURATION)
        if self.on_tap:
            self.on_tap(self)

    def _clear_flash(self, _dt) -> None:
        self.flash_color = (0, 0, 0, 0)

    # ── Long-press ────────────────────────────────────────────────────────────

    def _trigger_long_press(self) -> None:
        if self.on_long_press:
            self.on_long_press(self)

    # ── State machine ─────────────────────────────────────────────────────────

    def set_state(self, state: str, status_msg: str = "") -> None:
        self._state = state
        self.status_text = status_msg or state.upper()
        self._stop_animations()

        if state == "idle":
            self.panel_fill   = theme.PANEL_BG
            self.border_color = theme.BORDER_COLOR
            self.strip_color  = theme.STATUS_IDLE
            self.label_color  = theme.TEXT_COLOR
            self.icon_color   = theme.BORDER_COLOR

        elif state == "active":
            self.panel_fill   = theme.PANEL_BG_ACTIVE
            self.border_color = theme.BORDER_ACTIVE
            self.strip_color  = theme.STATUS_ACTIVE
            self.label_color  = theme.TEXT_ACTIVE
            self.icon_color   = theme.BORDER_ACTIVE
            self._start_pulse()

        elif state == "running":
            self.panel_fill   = theme.PANEL_BG_ACTIVE
            self.border_color = theme.BORDER_ACTIVE
            self.strip_color  = theme.STATUS_RUNNING
            self.label_color  = theme.TEXT_ACTIVE
            self.icon_color   = theme.BORDER_ACTIVE
            self._start_pulse()

        elif state == "error":
            self.border_color = theme.BORDER_ERROR
            self.strip_color  = theme.STATUS_ERROR
            self.label_color  = theme.TEXT_RED
            self._start_strobe()

    # ── Animations ────────────────────────────────────────────────────────────

    def _start_pulse(self) -> None:
        def _pulse(_dt) -> None:
            anim_in  = Animation(strip_color=theme.STATUS_RUNNING, duration=0.4)
            anim_out = Animation(strip_color=theme.STATUS_ACTIVE,  duration=0.4)
            (anim_in + anim_out).start(self)
        self._pulse_event = Clock.schedule_interval(_pulse, theme.PULSE_INTERVAL)

    def _start_strobe(self) -> None:
        def _toggle(_dt) -> None:
            self._strobe_state = not self._strobe_state
            if self._strobe_state:
                self.border_color = theme.BORDER_ERROR
                self.panel_fill   = (0.15, 0.0, 0.0, 1.0)
            else:
                self.border_color = theme.BORDER_ERROR_B
                self.panel_fill   = theme.PANEL_BG
        self._strobe_event = Clock.schedule_interval(_toggle, theme.STROBE_INTERVAL)

    def _stop_animations(self) -> None:
        if self._pulse_event:
            self._pulse_event.cancel()
            self._pulse_event = None
        if self._strobe_event:
            self._strobe_event.cancel()
            self._strobe_event = None
        Animation.cancel_all(self)
