# claude-console-gui

A native GTK4 + libadwaita terminal shell for the [Claude Code](https://claude.ai/code)
CLI, built for FreeBSD. It's laid out like the Claude desktop app: a sidebar
of sessions on the left, the selected session on the right, and a welcome
screen for picking a project folder. Each session is a real VTE terminal
running `claude` in that folder, styled with Claude's dark theme.

## Requirements (FreeBSD)

```sh
sudo pkg install vte3 libadwaita py312-pygobject
```

`python3.12`, `gtk4`, and `gobject-introspection` are pulled in as dependencies.

## Run

```sh
./claude-console-gui
```

## Install a desktop launcher + icon

```sh
./install.sh
```

Installs the `.desktop` entry and icon for the current user under
`~/.local/share/{applications,icons}` so "Claude Console" shows up in your
application launcher.

## Sessions

- **New session** opens the welcome screen. Pick a folder with
  **Open folder…**, start in your home folder, or click a recent folder.
- Session names follow the title Claude Code sets for the conversation. A
  spinner next to a session means Claude is working in it.
- Right-click a session to rename or close it; hover it for a close button.
- Narrow the window and the sidebar collapses into an overlay.

When `claude` exits in a session (e.g. `/exit` or Ctrl-D), the session drops
to a plain interactive shell instead of closing, so you can see the exit
output or relaunch it manually. Exiting that shell closes the session.

## Shortcuts

All shortcuts use Shift so plain Ctrl keys still reach Claude Code.

- `Ctrl+Shift+T` / `Ctrl+Shift+N`: new session
- `Ctrl+Shift+O`: open a folder in a new session
- `Ctrl+Shift+W`: close the current session
- `Ctrl+Shift+B`: show or hide the sidebar
- `Ctrl+PageUp` / `Ctrl+PageDown`: previous or next session

Recent folders are stored in `~/.config/claude-console-gui/recents.json`.
