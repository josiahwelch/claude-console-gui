"""Vte.Terminal construction and process spawning."""

import os

import gi

gi.require_version("Vte", "3.91")
from gi.repository import Gdk, GLib, Pango, Vte

# Claude-brand-inspired warm palette: terracotta accent on a dark, warm background
# instead of the default harsh green-on-black terminal look.
_BACKGROUND = "#1E1B18"
_FOREGROUND = "#F2ECE4"
_CURSOR = "#DA7756"

_PALETTE = [
    "#221F1C", "#C4635A", "#8FA876", "#D9A05B",
    "#6F9BC1", "#B98DBB", "#6FB3AE", "#E7E0D6",
    "#4A443E", "#E08278", "#A9C793", "#EFC17E",
    "#8FBBE0", "#D3ACD6", "#8FD1CB", "#F7F2EA",
]


def _rgba(hex_color):
    rgba = Gdk.RGBA()
    rgba.parse(hex_color)
    return rgba


def new_terminal():
    """Build a Vte.Terminal styled for the app; does not spawn a process yet."""
    terminal = Vte.Terminal()
    terminal.set_font(Pango.FontDescription.from_string("Monospace 11"))
    terminal.set_color_background(_rgba(_BACKGROUND))
    terminal.set_color_foreground(_rgba(_FOREGROUND))
    terminal.set_color_cursor(_rgba(_CURSOR))
    terminal.set_colors(_rgba(_FOREGROUND), _rgba(_BACKGROUND), [_rgba(c) for c in _PALETTE])
    terminal.set_scrollback_lines(10000)
    terminal.set_cursor_shape(Vte.CursorShape.BLOCK)
    terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)
    terminal.set_bold_is_bright(True)
    terminal.set_hexpand(True)
    terminal.set_vexpand(True)
    return terminal


def spawn_claude(terminal, working_directory=None, on_exit=None):
    """Spawn a login shell that launches `claude`, then drops to an interactive
    shell when it exits so the tab doesn't just vanish on /exit or Ctrl-D."""
    shell = os.environ.get("SHELL", "/bin/sh")
    working_directory = working_directory or os.path.expanduser("~")
    command = f"claude; exec {shell} -i"

    def on_spawn(term, pid, error, _data):
        if error is not None:
            term.feed(f"\r\nFailed to launch: {error.message}\r\n".encode())

    terminal.spawn_async(
        Vte.PtyFlags.DEFAULT,
        working_directory,
        [shell, "-lc", command],
        [],
        GLib.SpawnFlags.DEFAULT,
        None,
        None,
        -1,
        None,
        on_spawn,
        None,
    )

    if on_exit is not None:
        terminal.connect("child-exited", lambda term, status: on_exit(term, status))
