"""Adw.Application entry point: accent color, accelerators, window lifecycle."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from .window import ClaudeConsoleWindow

APP_ID = "io.josiahwelch.ClaudeConsoleGui"


class ClaudeConsoleApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        Adw.StyleManager.get_default().set_accent_color(Adw.AccentColor.ORANGE)
        self.set_accels_for_action("win.new-tab", ["<Primary><Shift>t"])
        self.set_accels_for_action("win.close-tab", ["<Primary><Shift>w"])

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = ClaudeConsoleWindow(self)
        window.present()


def main():
    app = ClaudeConsoleApplication()
    return app.run(None)
