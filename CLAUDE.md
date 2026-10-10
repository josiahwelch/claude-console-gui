# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A native GTK4 + libadwaita desktop chat app for Claude Code, laid out like
the Claude desktop app (sessions sidebar + chat transcript + composer).
Each session is not a library call — it's a `claude` CLI subprocess run in
headless `stream-json` mode, so the GUI is a protocol client/renderer over
stdin/stdout, not a reimplementation of any Claude Code logic. Primary
target is FreeBSD (via the Linuxulator `claude-code` port); developed on
macOS with Homebrew GTK4.

## Commands

There is no build step, test suite, linter, or package manifest in this
repo — it's plain Python 3.12 run directly against system GTK4/libadwaita.

```sh
./claude-console-gui          # run the app (needs PyGObject + GTK4 + libadwaita)
./install.sh                  # install desktop launcher/icon, check for missing deps
python3 -m py_compile claude_console_gui/*.py   # only available sanity check
```

There is no way to unit-test the GUI itself in this repo. The only
verification available before claiming a change works is `py_compile`
for syntax, plus actually launching the app in an environment with
GTK4/libadwaita/PyGObject installed and exercising the feature.

## Architecture

**Process boundary is the key structure.** `claude_process.py`'s
`ClaudeProcess` spawns `claude -p --input-format stream-json
--output-format stream-json --verbose --include-partial-messages
--permission-prompt-tool stdio` per session and speaks its line-delimited
JSON protocol over stdin/stdout:
- Outgoing: user messages (`type: "user"`) and `control_request`s
  (initialize, interrupt, set_permission_mode, set_model,
  control_response for permission answers).
- Incoming: `system`, `stream_event` (partial-message deltas),
  `assistant`, `user` (tool results), `result`, and `control_request`
  (`can_use_tool` — permission prompts, routed through the same channel
  Claude Code uses for AskUserQuestion and ExitPlanMode).

`chat.py`'s `ChatView` is the protocol consumer: `_on_event` dispatches
each incoming event type to a `_handle_*` method that mutates the
transcript (a `Gtk.Box` of widgets, not a model/view split — widgets ARE
the state). Key pieces:
- `_ToolCall`: collapsible row for a tool call, keyed by `tool_use_id` in
  `self._tools` so the later `tool_result` event can find it and fill in
  output/error state.
- `_PermissionCard`: renders differently depending on `tool_name` —
  `AskUserQuestion` and `ExitPlanMode` get bespoke UIs; everything else is
  a generic allow/deny/always-allow card. Responses go back through
  `ClaudeProcess.respond_permission`, which answers the specific
  `control_request` by `request_id`.
- Streaming text: `stream_event` deltas accumulate into
  `_stream_blocks[index]` and are throttled to one GTK render per 40ms via
  `GLib.timeout_add`, rather than re-rendering per token.
- `_replay`: saved transcript entries (read by `history.py`) have the same
  shape as live stream-json events, so resuming a past conversation reuses
  the exact same `_handle_*` handlers that live events use — this is why
  the replayed transcript and a live one look identical.

**`window.py`** owns app-level state the chat view doesn't: the sessions
list, the sidebar (`Adw.OverlaySplitView`), welcome screen, folder
picker/recents, and history search. `_Session` wraps one `ChatView` plus
its sidebar row/title; `ClaudeConsoleWindow` is the only place that knows
about multiple sessions at once — `ChatView` itself only knows about its
own folder and process.

**`history.py`** never talks to the live `claude` process. It reads
Claude Code's own saved transcripts from `~/.claude/projects/*/*.jsonl`
(or `$CLAUDE_CONFIG_DIR/projects`) directly off disk, on a background
thread (`History.scan_async`), reading only the head and tail bytes of
each file (titles/folder are near the top, latest title near the bottom)
to avoid loading entire conversation files just to build a list. Results
are cached by mtime so rescans only re-parse changed files.

**`markdown.py`** is a from-scratch Markdown → Pango markup renderer, not
a wrapped library — GTK labels render Pango markup, not HTML/CSS, so
standard Markdown libraries don't apply here. `MarkdownView.set_text` is
called repeatedly as text streams in; it diffs blocks by index and only
replaces widgets whose *kind* changed, so a growing code block doesn't
get rebuilt from scratch on every delta. `safe_markup` is a defensive
layer: a malformed/mismatched emphasis marker mid-stream must never blank
a label, so markup that fails `Pango.parse_markup` falls back to
plain-text-with-tags-stripped rather than raising.

**Styling** (`style.css`) is a single GTK CSS file loaded once at
`Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION` in `application.py`. GTK CSS is
a real but limited subset of CSS3 (no flexbox, limited animation) — check
what a selector/property actually does in GTK before assuming web-CSS
semantics apply.

## Conventions seen in this codebase

- Every module has a one-paragraph docstring at the top stating its single
  responsibility; keep that pattern for new modules.
- Widgets are built and wired in `__init__`; update methods (`set_input`,
  `set_result`, `set_text`, etc.) mutate existing widgets in place rather
  than rebuilding subtrees, since this app's whole UI model is "long-lived
  widgets mutated by streamed events."
- Dicts keyed by protocol IDs (`tool_use_id`, `request_id`) are the normal
  way state crosses from one `_handle_*` event to a later one — follow
  that pattern rather than introducing a separate state/model layer.
- Keep CLAUDE.md current by hand after changes that affect architecture
  or workflow — there's no automation regenerating it.
