# Changelog

## 0.5.0

- Conversation history: the sidebar has a searchable History list of past
  Claude Code conversations from every project, including ones started in
  the terminal.
- Clicking a past conversation replays its transcript and resumes it with
  `claude --resume` in its original folder.
- Closed sessions move into History. Open sessions are hidden from it.
- Saved "[Request interrupted by user]" messages show as an "Interrupted"
  divider.

## 0.4.0

- Sessions are now a chat interface instead of an embedded terminal. Each
  session runs `claude` in headless stream-json mode.
- Claude's replies stream in as formatted Markdown, with code blocks that
  have a copy button.
- Tool calls show as compact rows that expand to show the command, diff or
  output.
- Permission requests appear as cards with Deny / Always allow / Allow.
  Questions Claude asks (AskUserQuestion) and plans from plan mode get their
  own cards.
- Permission-mode and model pickers in the message box, switchable
  mid-conversation.
- The stop button or Escape interrupts a reply.
- If `claude` exits unexpectedly, the chat shows its error output and a
  Restart button that resumes the conversation.
- The welcome screen is now a message box with a project folder picker.
- Closing the window now quits the app and stops its `claude` processes.
- VTE is no longer required.
- README: new FreeBSD compatibility section covering the `claude-code`
  port, Linux compatibility setup, and the required versions.

## 0.3.0

- Redesigned to look like the Claude desktop app: a sessions sidebar
  (Adw.OverlaySplitView) replaces the tab bar, and the header shows the
  session title and its folder.
- New welcome screen: open a project folder, start in your home folder, or
  pick from recent folders.
- Session names follow the title Claude Code sets, with a spinner while
  Claude is working.
- Right-click a session to rename or close it; hover it for a close button.
- Claude dark theme throughout (charcoal surfaces, ivory text, Claude orange,
  serif display type), including the terminal colors.
- New shortcuts: Ctrl+Shift+O (open folder), Ctrl+Shift+B (toggle sidebar),
  Ctrl+PageUp/PageDown (switch sessions).
- The sidebar collapses into an overlay in narrow windows.

## 0.2.0

- Right-click a tab to rename it.

## 0.1.0

- Initial release: GTK4 + libadwaita tabbed terminal for Claude Code, app
  icon, desktop launcher, and install script.
