# claude-console-gui

A native GTK4 + libadwaita terminal shell for the [Claude Code](https://claude.ai/code)
CLI, built for FreeBSD. Each tab is a real VTE terminal running `claude` in a
login shell, styled with a warm terracotta-on-dark palette instead of a
default green-on-black terminal.

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

## Shortcuts

- `Ctrl+Shift+T` — new Claude session tab
- `Ctrl+Shift+W` — close current tab

When `claude` exits in a tab (e.g. `/exit` or Ctrl-D), the tab drops to a
plain interactive shell instead of closing, so you can see the exit output
or relaunch it manually.
