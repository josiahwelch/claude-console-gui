"""Adw.Application entry point: accent color, accelerators, window lifecycle."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from .window import ClaudeConsoleWindow

APP_ID = "io.josiahwelch.ClaudeConsoleGui"
STYLE_CSS = Path(__file__).with_name("style.css")


class ClaudeConsoleApplication(Adw.Application):
    def __init__(self):
        # Sets X11 WM_CLASS so window managers can match this window to the
        # installed .desktop file's StartupWMClass and resolve its icon.
        GLib.set_prgname(APP_ID)
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.hold()
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        provider = Gtk.CssProvider()
        provider.load_from_path(str(STYLE_CSS))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

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
