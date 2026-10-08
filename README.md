# claude-console-gui

A native GTK4 + libadwaita chat app for [Claude Code](https://claude.ai/code),
built for FreeBSD and laid out like the Claude desktop app: a sidebar of
sessions, a chat transcript, and a message box with permission-mode and model
pickers. Under the hood each session runs the `claude` CLI in headless
stream-json mode, so it uses your existing Claude Code login, settings,
`CLAUDE.md` files, MCP servers and plugins.

## Features

- **Chat transcript:** Claude's replies stream in as formatted Markdown
  (headings, lists, tables, links, and code blocks with a copy button).
- **Tool calls:** each one appears as a compact row (for example
  "Edit src/main.py") with a spinner while it runs. Click it to see the
  command, diff or output.
- **Permission prompts:** when Claude needs approval, a card shows what it
  wants to do, with **Deny**, **Always allow** and **Allow** buttons.
  Questions Claude asks you (AskUserQuestion) and plans from plan mode get
  their own cards.
- **Permission modes:** Ask permissions, Accept edits, Plan mode, or Bypass
  permissions. You can switch mid-conversation from the message box.
- **Model picker:** the default model, Opus, Sonnet or Haiku.
- **Sessions sidebar:** sessions are named after your first message, show a
  spinner while Claude works, and can be renamed or closed from a right-click
  menu.
- **Conversation history:** the sidebar lists your past Claude Code
  conversations, newest first, from every project. That includes ones you
  started in the terminal. Click one to reopen it, with the earlier messages
  shown, and keep going. Search filters by title or folder.
- **Stop** a reply with the stop button or Escape.
- If `claude` exits unexpectedly, its error output is shown in the chat with
  a **Restart session** button that resumes the conversation.

## FreeBSD compatibility

> **Status: not yet tested on FreeBSD.** Development and testing so far have
> been on macOS with Homebrew's GTK4 and libadwaita. The app uses only
> portable GTK/libadwaita APIs and plain Python, so it should work on
> FreeBSD. If something breaks there, please open an issue with the error
> output.

### What the app needs

| Component | Minimum | FreeBSD package |
| --- | --- | --- |
| Python | 3.12 | `python312` (pulled in by `py312-pygobject`) |
| PyGObject | for Python 3.12 | `py312-pygobject` |
| GTK | 4.10 (for `Gtk.FileDialog`) | `gtk4` (pulled in by `libadwaita`) |
| libadwaita | 1.5 (for `Adw.AlertDialog`) | `libadwaita` |
| Icons | — | `adwaita-icon-theme` |
| Claude Code | a version with `--input-format stream-json` | `claude-code` |

VTE is no longer needed: v0.4.0 replaced the embedded terminal with the
chat view.

### Installing Claude Code on FreeBSD

Anthropic doesn't ship a native FreeBSD build of Claude Code. The
[`misc/claude-code`](https://www.freshports.org/misc/claude-code/) port
packages the Linux build to run under FreeBSD's Linux compatibility layer
(Linuxulator). It's available for amd64 and aarch64 only.

```sh
sudo sysrc linux_enable=YES
```

```sh
sudo service linux start
```

```sh
sudo pkg install claude-code
```

Then run `claude` once in a terminal to sign in. The chat view can't show
the interactive login screen, so sessions fail until you've signed in once.

The port's `claude` wrapper checks that the Linux compatibility mounts are in
place (`linprocfs`, and `fdescfs` mounted with `linrdlnk`). Without them,
Claude Code can hang. `service linux start` sets these up. If one is
missing, the wrapper's error message appears in the chat when a session
starts.

### Other FreeBSD notes

- **`claude` not on the launcher's PATH:** apps started from a desktop
  launcher often get a shorter PATH than your shell. If `claude` isn't on it,
  the app also looks in `~/.local/bin`, `~/.claude/local` and
  `/usr/local/bin`.
- **Folder picker:** without `xdg-desktop-portal`, **Choose another folder…**
  uses GTK's built-in file chooser. That's expected.
- **Fonts:** headings use a serif font (Source Serif 4 is the closest match
  to Claude's). Install it or any other serif font. Otherwise GTK falls
  back to its default serif.

## Install and run

```sh
sudo pkg install libadwaita py312-pygobject adwaita-icon-theme
```

```sh
./claude-console-gui
```

To add "Claude Console" to your application launcher, run the install
script. It installs the `.desktop` entry and icon under
`~/.local/share/{applications,icons}` and reports any missing packages.

```sh
./install.sh
```

## Using it

- **Start a session** from the welcome screen: type a message, pick the
  project folder from the folder menu (recent folders are listed), and press
  Enter. Each session runs `claude` in its folder.
- **Enter** sends the message and **Shift+Enter** inserts a new line.
  Slash commands like `/compact` can be sent as messages.
- **Rename or close a session** by right-clicking it in the sidebar, or hover
  over it for a close button. Closed sessions move to **History**.
- **Resume a past conversation** by clicking it under **History**. It reopens
  in its original folder with `claude --resume`, so Claude has the full
  context. If that folder no longer exists, the app tells you instead.
- **Narrow windows** collapse the sidebar into an overlay.

### Shortcuts

- `Ctrl+Shift+T` / `Ctrl+Shift+N`: new session
- `Ctrl+Shift+O`: choose a folder for a new session
- `Ctrl+Shift+W`: close the current session
- `Ctrl+Shift+B`: show or hide the sidebar
- `Ctrl+PageUp` / `Ctrl+PageDown`: previous or next session
- `Escape`: stop Claude's current reply

Recent folders are stored in `~/.config/claude-console-gui/recents.json`.

### Where history comes from

The app doesn't keep its own copy of your conversations. It reads the
transcripts Claude Code already saves under `~/.claude/projects` (or
`$CLAUDE_CONFIG_DIR/projects`). To build the list it reads only the start
and end of each file, on a background thread, and caches the results. A
conversation's title is its `/rename` name if it has one, then Claude Code's
auto-generated title, then your first message.

## How it works

Each session starts the CLI like this:

```sh
claude -p --input-format stream-json --output-format stream-json --verbose --include-partial-messages --permission-prompt-tool stdio
```

Messages go to `claude` as JSON lines on stdin. Streamed text, tool calls,
tool results and permission requests (`can_use_tool` control requests) come
back on stdout. The app answers permission requests from the cards in the
chat, and uses the same control channel to interrupt a reply and to change
the permission mode or model.
