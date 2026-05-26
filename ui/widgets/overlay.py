"""
Onikiri Mk.I — Advanced Options Overlay
Fullscreen overlay shown on long-press of a module panel.
Lists all commands available on that module with one-tap execution.
"""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.floatlayout import FloatLayout
from kivy.properties import StringProperty

from ui import theme


class CommandRow(BoxLayout):
    cmd_name = StringProperty("")
    cmd_desc = StringProperty("")

    def __init__(self, name: str, desc: str, on_exec, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cmd_name = name
        self.cmd_desc = desc
        self._on_exec = on_exec

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            if self._on_exec:
                self._on_exec(self.cmd_name)
            return True
        return super().on_touch_up(touch)


class AdvancedOverlay(BoxLayout):
    module_label = StringProperty("")

    def __init__(self, module_label: str, commands: dict[str, str],
                 on_execute, **kwargs) -> None:
        super().__init__(**kwargs)
        self.module_label = module_label
        self._on_execute = on_execute
        self._build(commands)

    def _build(self, commands: dict[str, str]) -> None:
        grid = self.ids.get("command_grid")
        if grid is None:
            return
        grid.clear_widgets()
        for cmd_name, cmd_desc in commands.items():
            row = CommandRow(
                name=cmd_name,
                desc=cmd_desc,
                on_exec=self._execute,
            )
            grid.add_widget(row)

    def _execute(self, cmd_name: str) -> None:
        self.dismiss()
        if self._on_execute:
            self._on_execute(cmd_name)

    def dismiss(self) -> None:
        parent = self.parent
        if parent is not None:
            parent.remove_widget(self)
