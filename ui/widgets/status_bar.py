"""
Onikiri Mk.I — Status Bar Widget
Top-edge strip showing device name, active job summary, and time.
"""

from __future__ import annotations

import time

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout


class OnikiriStatusBar(BoxLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._clock = None

    def on_kv_post(self, _base_widget) -> None:
        self._clock = Clock.schedule_interval(self._tick, 10)
        self._tick(0)

    def _tick(self, _dt) -> None:
        label = self.ids.get("label_time")
        if label:
            label.text = time.strftime("%H:%M")

    def set_status(self, text: str) -> None:
        label = self.ids.get("label_status")
        if label:
            label.text = text.upper()[:48]
