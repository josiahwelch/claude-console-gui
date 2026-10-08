"""Vte.Terminal construction and process spawning."""

import os

import gi

gi.require_version("Vte", "3.91")
from gi.repository import Gdk, GLib, Pango, Vte

# Matches the Claude desktop app's dark theme so the terminal blends into the
# surrounding chrome: warm charcoal background, ivory text, Claude orange.
_BACKGROUND = "#262624"
_FOREGROUND = "#FAF9F5"
_CURSOR = "#D97757"

_PALETTE = [
    "#30302E", "#C4635A", "#8FA876", "#D9A05B",
    "#6F9BC1", "#B98DBB", "#6FB3AE", "#E7E0D6",
    "#5A5852", "#E08278", "#A9C793", "#EFC17E",
    "#8FBBE0", "#D3ACD6", "#8FD1CB", "#FAF9F5",
]


def _rgba(hex_color):
    rgba = Gdk.RGBA()
    rgba.parse(hex_color)
    return rgba


def new_terminal():
    """Build a Vte.Terminal styled for the app; does not spawn a process yet."""
    terminal = Vte.Terminal()
    terminal.set_font(Pango.FontDescription.from_string("Monospace 10.5"))
    terminal.set_color_background(_rgba(_BACKGROUND))
    terminal.set_color_foreground(_rgba(_FOREGROUND))
    terminal.set_color_cursor(_rgba(_CURSOR))
    terminal.set_colors(_rgba(_FOREGROUND), _rgba(_BACKGROUND), [_rgba(c) for c in _PALETTE])
    terminal.set_scrollback_lines(10000)
    terminal.set_cursor_shape(Vte.CursorShape.BLOCK)
    terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)
    terminal.set_bold_is_bright(True)
    terminal.add_css_class("claude-terminal")
    terminal.set_hexpand(True)
    terminal.set_vexpand(True)
    return terminal


def spawn_claude(terminal, working_directory=None, on_exit=None):
    """Spawn /bin/sh to launch `claude`, then drop to an interactive shell
    when it exits so the tab doesn't just vanish on /exit or Ctrl-D."""
    working_directory = working_directory or os.path.expanduser("~")
    command = "claude; exec /bin/sh -i"

    def on_spawn(term, pid, error, _data):
        if error is not None:
            term.feed(f"\r\nFailed to launch: {error.message}\r\n".encode())

    terminal.spawn_async(
        Vte.PtyFlags.DEFAULT,
        working_directory,
        ["/bin/sh", "-c", command],
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


def _is_spinner(char):
    # Claude Code prefixes its title with a braille spinner frame while working
    # and with a star glyph like "✳" when idle.
    return "\u2800" <= char <= "\u28ff"


def connect_title(terminal, callback):
    """Call callback(title, busy) whenever the program running in the terminal
    sets the window title. title is "" for the generic "Claude Code" title."""

    def on_title_changed(term):
        raw = (term.get_window_title() or "").strip()
        busy = bool(raw) and _is_spinner(raw[0])
        start = 0
        while start < len(raw) and not raw[start].isalnum():
            start += 1
        title = raw[start:].strip()
        if title == "Claude Code":
            title = ""
        callback(title, busy)

    terminal.connect("window-title-changed", on_title_changed)
