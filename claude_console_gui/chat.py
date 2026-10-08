"""The chat interface for one Claude Code session: a scrolling transcript of
messages, tool calls and permission requests above a message composer."""

import json
import os

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from .claude_process import ClaudeProcess
from .markdown import MarkdownView, safe_markup

PERMISSION_MODES = [
    ("Ask permissions", "default"),
    ("Accept edits", "acceptEdits"),
    ("Plan mode", "plan"),
    ("Bypass permissions", "bypassPermissions"),
]

MODELS = [
    ("Default model", None),
    ("Opus", "opus"),
    ("Sonnet", "sonnet"),
    ("Haiku", "haiku"),
]

_TOOL_ICONS = {
    "Bash": "utilities-terminal-symbolic",
    "Read": "document-open-symbolic",
    "Write": "document-new-symbolic",
    "Edit": "document-edit-symbolic",
    "MultiEdit": "document-edit-symbolic",
    "NotebookEdit": "document-edit-symbolic",
    "Grep": "system-search-symbolic",
    "Glob": "system-search-symbolic",
    "WebFetch": "web-browser-symbolic",
    "WebSearch": "web-browser-symbolic",
    "Task": "system-run-symbolic",
    "Agent": "system-run-symbolic",
    "TodoWrite": "view-list-symbolic",
}

_MAX_OUTPUT_CHARS = 6000


def _mono_label(text="", markup=False):
    label = Gtk.Label(xalign=0, yalign=0, selectable=True, wrap=True, wrap_mode=Pango.WrapMode.CHAR)
    label.add_css_class("monospace")
    label.add_css_class("tool-text")
    if markup:
        label.set_markup(text)
    else:
        label.set_label(text)
    return label


def _truncate(text, limit=_MAX_OUTPUT_CHARS):
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… ({len(text) - limit} more characters)"


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, dict) and item.get("type") == "image":
                parts.append("[image]")
        return "\n".join(parts)
    return json.dumps(content, indent=2)


def _diff_markup(old, new):
    lines = []
    for line in old.splitlines():
        lines.append(f'<span foreground="#E08278">- {GLib.markup_escape_text(line)}</span>')
    for line in new.splitlines():
        lines.append(f'<span foreground="#A9C793">+ {GLib.markup_escape_text(line)}</span>')
    return "\n".join(lines)


class _ToolDescriber:
    """Turns a tool name and input into human-readable summary text."""

    def __init__(self, folder):
        self.folder = folder

    def path(self, path):
        if not path:
            return ""
        try:
            rel = os.path.relpath(path, self.folder)
        except ValueError:
            return path
        return path if rel.startswith("..") else rel

    def summary(self, name, tool_input):
        i = tool_input or {}
        if name == "Bash":
            command_lines = (i.get("command") or "").splitlines()
            return i.get("description") or (command_lines[0] if command_lines else "")
        if name in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
            return self.path(i.get("file_path") or i.get("notebook_path"))
        if name in ("Grep", "Glob"):
            return i.get("pattern", "")
        if name == "WebFetch":
            return i.get("url", "")
        if name == "WebSearch":
            return i.get("query", "")
        if name in ("Task", "Agent"):
            return i.get("description", "")
        if name == "TodoWrite":
            todos = i.get("todos") or []
            done = sum(1 for t in todos if t.get("status") == "completed")
            return f"{done}/{len(todos)} done"
        for value in i.values():
            if isinstance(value, str):
                return value.splitlines()[0] if value else ""
        return ""

    def details(self, name, tool_input):
        """Pango markup describing the input in full."""
        i = tool_input or {}
        if name == "Bash":
            return GLib.markup_escape_text("$ " + i.get("command", ""))
        if name == "Edit":
            return _diff_markup(i.get("old_string", ""), i.get("new_string", ""))
        if name == "MultiEdit":
            return "\n\n".join(_diff_markup(e.get("old_string", ""), e.get("new_string", "")) for e in i.get("edits", []))
        if name == "Write":
            return GLib.markup_escape_text(_truncate(i.get("content", "")))
        if name == "TodoWrite":
            marks = {"completed": "☑", "in_progress": "◐"}
            return "\n".join(
                GLib.markup_escape_text(marks.get(t.get("status"), "☐") + " " + t.get("content", ""))
                for t in i.get("todos", [])
            )
        return GLib.markup_escape_text(_truncate(json.dumps(i, indent=2)))

    def permission_heading(self, name, tool_input):
        target = self.summary(name, tool_input)
        if name == "Bash":
            return "Claude wants to run a command"
        if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            return f"Claude wants to edit {target}" if target else "Claude wants to edit a file"
        if name == "Read":
            return f"Claude wants to read {target}"
        if name == "WebFetch":
            return "Claude wants to fetch a web page"
        if name == "WebSearch":
            return "Claude wants to search the web"
        return f"Claude wants to use {name}"


class _ToolCall(Gtk.Box):
    """A collapsed one-line summary of a tool call that expands to show its
    input and output."""

    def __init__(self, name, describer):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("tool-call")
        self.name = name
        self.describer = describer

        icon = Gtk.Image.new_from_icon_name(_TOOL_ICONS.get(name, "emblem-system-symbolic"))
        icon.add_css_class("tool-icon")
        self.title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, use_markup=True)
        self.spinner = Gtk.Spinner(spinning=True)
        self.status = Gtk.Image(visible=False)
        self.chevron = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        self.chevron.add_css_class("dim-label")

        header_box = Gtk.Box(spacing=8)
        header_box.append(icon)
        header_box.append(self.title)
        header_box.append(self.spinner)
        header_box.append(self.status)
        header_box.append(self.chevron)
        header = Gtk.Button(child=header_box)
        header.add_css_class("flat")
        header.add_css_class("tool-header")
        header.connect("clicked", lambda _b: self.set_expanded(not self.revealer.get_reveal_child()))

        self.input_label = _mono_label()
        self.output_label = _mono_label()
        self.output_label.set_visible(False)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        details.add_css_class("tool-details")
        details.append(self.input_label)
        details.append(self.output_label)
        self.revealer = Gtk.Revealer(child=details, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)

        self.append(header)
        self.append(self.revealer)
        self.set_input({})

    def set_expanded(self, expanded):
        self.revealer.set_reveal_child(expanded)
        self.chevron.set_from_icon_name("pan-down-symbolic" if expanded else "pan-end-symbolic")

    def set_input(self, tool_input):
        summary = self.describer.summary(self.name, tool_input)
        markup = f"<b>{GLib.markup_escape_text(self.name)}</b>"
        if summary:
            markup += f"  <span foreground='#A6A39A'>{GLib.markup_escape_text(summary)}</span>"
        self.title.set_markup(markup)
        self.input_label.set_markup(safe_markup(self.describer.details(self.name, tool_input)))
        if self.name == "TodoWrite":
            self.set_expanded(True)

    def set_result(self, content, is_error):
        self.spinner.set_spinning(False)
        self.spinner.set_visible(False)
        self.status.set_visible(True)
        if is_error:
            self.status.set_from_icon_name("dialog-error-symbolic")
            self.status.add_css_class("error")
        else:
            self.status.set_from_icon_name("object-select-symbolic")
            self.status.add_css_class("success")
        text = _truncate(_result_text(content).strip())
        self.output_label.set_label(text)
        self.output_label.set_visible(bool(text))
        if is_error:
            self.output_label.add_css_class("error")

    def cancel(self):
        if self.spinner.get_spinning():
            self.spinner.set_spinning(False)
            self.spinner.set_visible(False)


class _PermissionCard(Gtk.Box):
    """Asks the user to approve a tool call, answer Claude's questions, or
    approve a plan, then collapses to a one-line record of the decision."""

    def __init__(self, request, describer, respond, on_plan_approved):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("permission-card")
        self.request = request
        self._respond = respond
        self._on_plan_approved = on_plan_approved
        self.tool_name = request.get("tool_name", "")
        self.tool_input = request.get("input") or {}

        if self.tool_name == "AskUserQuestion":
            self._build_questions()
        elif self.tool_name == "ExitPlanMode":
            self._build_plan()
        else:
            self._build_permission(describer)

    def _heading(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class("permission-heading")
        self.append(label)

    def _buttons(self, *buttons):
        box = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        for label, style, callback in buttons:
            button = Gtk.Button(label=label)
            button.add_css_class("pill")
            if style:
                button.add_css_class(style)
            button.connect("clicked", lambda _b, cb=callback: cb())
            box.append(button)
        self.button_box = box
        self.append(box)

    def _build_permission(self, describer):
        self._heading(describer.permission_heading(self.tool_name, self.tool_input))
        detail = _mono_label(safe_markup(describer.details(self.tool_name, self.tool_input)), markup=True)
        frame = Gtk.ScrolledWindow(child=detail, propagate_natural_height=True, max_content_height=260)
        frame.add_css_class("permission-detail")
        self.append(frame)

        suggestions = self.request.get("permission_suggestions") or []
        buttons = [("Deny", None, lambda: self._finish(False, "Denied"))]
        if suggestions:
            buttons.append((
                "Always allow",
                None,
                lambda: self._finish(True, "Always allowed", updated_permissions=suggestions),
            ))
        buttons.append(("Allow", "suggested-action", lambda: self._finish(True, "Allowed")))
        self._buttons(*buttons)

    def _build_plan(self):
        self._heading("Claude has a plan. Ready to start?")
        plan = MarkdownView(self.tool_input.get("plan", ""))
        plan.add_css_class("plan-view")
        self.append(plan)

        def approve():
            self._finish(True, "Plan approved")
            self._on_plan_approved()

        self._buttons(
            ("Keep planning", None, lambda: self._finish(False, "Kept planning", message="The user wants to keep planning. Ask what to change.")),
            ("Approve plan", "suggested-action", approve),
        )

    def _build_questions(self):
        self._answers = []
        for question in self.tool_input.get("questions", []):
            text = question.get("question", "")
            header = question.get("header")
            if header:
                chip = Gtk.Label(label=header, xalign=0)
                chip.add_css_class("question-chip")
                self.append(chip)
            self._heading(text)

            multi = question.get("multiSelect", False)
            group = None
            checks = []
            for option in question.get("options", []):
                check = Gtk.CheckButton()
                if not multi:
                    if group is None:
                        group = check
                    else:
                        check.set_group(group)
                label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                title = Gtk.Label(label=option.get("label", ""), xalign=0, wrap=True)
                label_box.append(title)
                if option.get("description"):
                    desc = Gtk.Label(label=option["description"], xalign=0, wrap=True)
                    desc.add_css_class("dim-label")
                    desc.add_css_class("caption")
                    label_box.append(desc)
                check.set_child(label_box)
                check.add_css_class("question-option")
                self.append(check)
                checks.append((check, option.get("label", "")))

            other = Gtk.Entry(placeholder_text="Other…")
            self.append(other)
            self._answers.append((text, checks, other))

        self._buttons(
            ("Skip", None, lambda: self._finish(False, "Skipped", message="The user declined to answer.")),
            ("Submit", "suggested-action", self._submit_answers),
        )

    def _submit_answers(self):
        answers = {}
        for text, checks, other in self._answers:
            chosen = [label for check, label in checks if check.get_active()]
            if other.get_text().strip():
                chosen.append(other.get_text().strip())
            answers[text] = ", ".join(chosen)
        summary = "; ".join(v for v in answers.values() if v) or "No answer"
        self._finish(True, f"Answered: {summary}", updated_input={**self.tool_input, "answers": answers})

    def _finish(self, allow, outcome, updated_input=None, updated_permissions=None, message=None):
        self._respond(
            self.request,
            allow,
            updated_input if updated_input is not None else self.tool_input,
            updated_permissions,
            message,
        )
        self.resolve(outcome, allow)

    def resolve(self, outcome, allowed=True):
        while (child := self.get_first_child()) is not None:
            self.remove(child)
        self.remove_css_class("permission-card")
        self.add_css_class("permission-outcome")
        icon = Gtk.Image.new_from_icon_name("object-select-symbolic" if allowed else "action-unavailable-symbolic")
        label = Gtk.Label(label=f"{self.tool_name}: {outcome}", xalign=0, wrap=True)
        label.add_css_class("dim-label")
        row = Gtk.Box(spacing=8)
        row.append(icon)
        row.append(label)
        self.append(row)


class Composer(Gtk.Box):
    """The rounded message box: a growing text area with controls below it.
    Enter sends, Shift+Enter inserts a newline."""

    def __init__(self, placeholder, on_submit, on_stop=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("composer")
        self._on_submit = on_submit
        self._on_stop = on_stop
        self._busy = False

        self.text_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        self.text_view.add_css_class("composer-text")
        self.buffer = self.text_view.get_buffer()

        self.placeholder = Gtk.Label(label=placeholder, xalign=0, yalign=0, can_target=False)
        self.placeholder.add_css_class("composer-placeholder")
        self.buffer.connect("changed", self._on_changed)

        overlay = Gtk.Overlay(child=self.text_view)
        overlay.add_overlay(self.placeholder)
        scroller = Gtk.ScrolledWindow(
            child=overlay,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
            max_content_height=220,
        )

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.text_view.add_controller(keys)

        self.send_button = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Send (Enter)", sensitive=False)
        self.send_button.add_css_class("circular")
        self.send_button.add_css_class("send-button")
        self.send_button.connect("clicked", lambda _b: self._on_send_clicked())

        self.controls = Gtk.Box(spacing=4)
        spacer = Gtk.Box(hexpand=True)
        bottom = Gtk.Box(spacing=4)
        bottom.add_css_class("composer-controls")
        bottom.append(self.controls)
        bottom.append(spacer)
        bottom.append(self.send_button)

        self.append(scroller)
        self.append(bottom)

    def grab_focus(self):
        return self.text_view.grab_focus()

    def get_text(self):
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, False)

    def set_busy(self, busy):
        self._busy = busy
        if busy:
            self.send_button.set_icon_name("media-playback-stop-symbolic")
            self.send_button.set_tooltip_text("Stop")
            self.send_button.set_sensitive(True)
        else:
            self.send_button.set_icon_name("go-up-symbolic")
            self.send_button.set_tooltip_text("Send (Enter)")
            self._on_changed(self.buffer)

    def _on_changed(self, buffer):
        empty = buffer.get_char_count() == 0
        self.placeholder.set_visible(empty)
        if not self._busy:
            self.send_button.set_sensitive(not empty)

    def _on_key(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (state & Gdk.ModifierType.SHIFT_MASK):
            self._submit()
            return True
        return False

    def _on_send_clicked(self):
        if self._busy and self.buffer.get_char_count() == 0 and self._on_stop:
            self._on_stop()
        else:
            self._submit()

    def _submit(self):
        text = self.get_text().strip()
        if not text:
            return
        self.buffer.set_text("")
        self._on_submit(text)


def make_dropdown(options, tooltip):
    dropdown = Gtk.DropDown.new_from_strings([label for label, _value in options])
    dropdown.set_tooltip_text(tooltip)
    dropdown.add_css_class("flat")
    dropdown.add_css_class("composer-dropdown")
    return dropdown


class ChatView(Gtk.Box):
    """One session's transcript and composer, driving a ClaudeProcess."""

    def __init__(self, folder, on_title, on_busy, model=None, permission_mode="default"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.folder = folder
        self._on_title = on_title
        self._on_busy = on_busy
        self.describer = _ToolDescriber(folder)
        self.process = None
        self.session_id = None
        self.busy = False
        self._titled = False
        self._stick_to_bottom = True
        self._tools = {}
        self._permission_cards = {}
        self._streamed_messages = set()
        self._stream_message = None
        self._stream_blocks = {}
        self._render_pending = set()

        self.transcript = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.transcript.add_css_class("transcript")

        self.working = Gtk.Box(spacing=10, visible=False)
        self.working.add_css_class("working")
        self.working_spinner = Gtk.Spinner()
        self.working_label = Gtk.Label(label="Thinking…", xalign=0)
        self.working.append(self.working_spinner)
        self.working.append(self.working_label)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        column.append(self.transcript)
        column.append(self.working)

        clamp = _clamp(column)
        self.scroller = Gtk.ScrolledWindow(child=clamp, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        adjustment = self.scroller.get_vadjustment()
        adjustment.connect("value-changed", self._on_scrolled)
        adjustment.connect("changed", self._on_content_resized)

        self.composer = Composer("Reply to Claude…", self.send, on_stop=self.stop_turn)
        self.mode_dropdown = make_dropdown(PERMISSION_MODES, "Permission mode")
        self.mode_dropdown.set_selected([v for _l, v in PERMISSION_MODES].index(permission_mode))
        self.mode_dropdown.connect("notify::selected", self._on_mode_changed)
        self.model_dropdown = make_dropdown(MODELS, "Model")
        self.model_dropdown.set_selected([v for _l, v in MODELS].index(model))
        self.model_dropdown.connect("notify::selected", self._on_model_changed)
        self.composer.controls.append(self.mode_dropdown)
        self.composer.controls.append(self.model_dropdown)

        composer_clamp = _clamp(self.composer)
        composer_clamp.add_css_class("composer-area")

        self.append(self.scroller)
        self.append(composer_clamp)

        self._start_process()

    # -- Process lifecycle ----------------------------------------------------

    def _start_process(self, resume=None):
        mode = PERMISSION_MODES[self.mode_dropdown.get_selected()][1]
        model = MODELS[self.model_dropdown.get_selected()][1]
        try:
            self.process = ClaudeProcess(
                self.folder, self._on_event, self._on_process_exit,
                model=model, permission_mode=mode, resume=resume,
            )
        except (GLib.Error, FileNotFoundError) as error:
            self.process = None
            message = getattr(error, "message", None) or str(error)
            self._add_notice(
                "Couldn't start Claude Code",
                f"{message}\n\nInstall Claude Code (on FreeBSD: sudo pkg install claude-code) "
                "and run `claude` once in a terminal to sign in.",
                error=True,
            )

    def shutdown(self):
        if self.process is not None:
            self.process.stop()
            self.process = None

    def _on_process_exit(self, status, stderr):
        self.process = None
        self._set_busy(False)
        for tool in self._tools.values():
            tool.cancel()
        body = stderr or f"The claude process exited with status {status}."
        notice = self._add_notice("Claude Code stopped", body, error=True)
        restart = Gtk.Button(label="Restart session", halign=Gtk.Align.START)
        restart.add_css_class("pill")
        restart.connect("clicked", lambda b: (b.set_sensitive(False), self._start_process(resume=self.session_id)))
        notice.append(restart)

    # -- Sending --------------------------------------------------------------

    def send(self, text):
        if self.process is None:
            self._start_process(resume=self.session_id)
            if self.process is None:
                return
        if not self._titled:
            self._titled = True
            first_line = text.strip().splitlines()[0]
            self._on_title(first_line[:60] + ("…" if len(first_line) > 60 else ""))
        self._add_user_message(text)
        self.process.send_user_message(text)
        self._stick_to_bottom = True
        self._set_busy(True, "Thinking…")

    def stop_turn(self):
        if self.process is not None and self.busy:
            self.process.interrupt()
            self.working_label.set_label("Stopping…")

    def _on_mode_changed(self, dropdown, _pspec):
        if self.process is not None:
            self.process.set_permission_mode(PERMISSION_MODES[dropdown.get_selected()][1])

    def _on_model_changed(self, dropdown, _pspec):
        if self.process is not None:
            self.process.set_model(MODELS[dropdown.get_selected()][1])

    def _respond_permission(self, request, allow, updated_input, updated_permissions, message):
        if self.process is not None:
            self.process.respond_permission(request["request_id"], allow, updated_input, updated_permissions, message)
        self._permission_cards.pop(request["request_id"], None)
        if self.busy:
            self.working.set_visible(True)

    def _on_plan_approved(self):
        self.mode_dropdown.set_selected(0)

    # -- Transcript widgets ---------------------------------------------------

    def _append(self, widget):
        self.transcript.append(widget)
        return widget

    def _add_user_message(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True)
        label.set_max_width_chars(70)
        bubble = Gtk.Box(halign=Gtk.Align.END)
        bubble.add_css_class("user-bubble")
        bubble.append(label)
        self._append(bubble)

    def _add_assistant_text(self, text=""):
        view = MarkdownView(text)
        view.add_css_class("assistant-text")
        return self._append(view)

    def _add_notice(self, heading, body, error=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("notice")
        if error:
            box.add_css_class("notice-error")
        title = Gtk.Label(label=heading, xalign=0)
        title.add_css_class("heading")
        box.append(title)
        if body:
            box.append(_mono_label(body.strip()))
        return self._append(box)

    def _add_divider(self, text):
        label = Gtk.Label(label=text)
        label.add_css_class("dim-label")
        label.add_css_class("caption")
        return self._append(label)

    def _set_busy(self, busy, status=None):
        self.busy = busy
        self.composer.set_busy(busy)
        self.working.set_visible(busy and not self._permission_cards)
        self.working_spinner.set_spinning(busy)
        if status:
            self.working_label.set_label(status)
        self._on_busy(busy)

    # -- Scrolling ------------------------------------------------------------

    def _on_scrolled(self, adjustment):
        bottom = adjustment.get_upper() - adjustment.get_page_size()
        self._stick_to_bottom = adjustment.get_value() >= bottom - 48

    def _on_content_resized(self, adjustment):
        if self._stick_to_bottom:
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())

    # -- Protocol events ------------------------------------------------------

    def _on_event(self, event):
        kind = event.get("type")
        if event.get("parent_tool_use_id"):
            return  # subagent traffic; its parent Task call summarises it
        handler = getattr(self, f"_handle_{kind}", None)
        if handler is not None:
            handler(event)

    def _handle_system(self, event):
        subtype = event.get("subtype")
        if subtype == "init":
            self.session_id = event.get("session_id") or self.session_id
        elif subtype == "compact_boundary":
            self._add_divider("Conversation compacted")

    def _handle_stream_event(self, event):
        stream = event.get("event") or {}
        kind = stream.get("type")
        if kind == "message_start":
            self._stream_message = (stream.get("message") or {}).get("id")
            self._stream_blocks = {}
        elif kind == "content_block_start":
            block = stream.get("content_block") or {}
            index = stream.get("index")
            if block.get("type") == "text":
                self._streamed_messages.add(self._stream_message)
                self._stream_blocks[index] = [self._add_assistant_text(), block.get("text", "")]
                self.working_label.set_label("Writing…")
            elif block.get("type") == "thinking":
                self.working_label.set_label("Thinking…")
            elif block.get("type") == "tool_use":
                self._tool(block.get("id"), block.get("name", "Tool"))
                self.working_label.set_label(f"Running {block.get('name', 'tool')}…")
        elif kind == "content_block_delta":
            delta = stream.get("delta") or {}
            entry = self._stream_blocks.get(stream.get("index"))
            if entry is not None and delta.get("type") == "text_delta":
                entry[1] += delta.get("text", "")
                self._schedule_render(stream.get("index"))

    def _schedule_render(self, index):
        if index in self._render_pending:
            return
        self._render_pending.add(index)

        def render(blocks=self._stream_blocks):
            self._render_pending.discard(index)
            entry = blocks.get(index)
            if entry is not None:
                entry[0].set_text(entry[1])
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(40, render)

    def _handle_assistant(self, event):
        message = event.get("message") or {}
        streamed = message.get("id") in self._streamed_messages
        for block in message.get("content") or []:
            kind = block.get("type")
            if kind == "text" and not streamed and block.get("text"):
                self._add_assistant_text(block["text"])
            elif kind == "tool_use":
                self._tool(block.get("id"), block.get("name", "Tool")).set_input(block.get("input"))
        if event.get("error"):
            self._add_notice("Error", str(event.get("error")), error=True)

    def _handle_user(self, event):
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool = self._tools.get(block.get("tool_use_id"))
                if tool is not None:
                    tool.set_result(block.get("content"), bool(block.get("is_error")))
        self.working_label.set_label("Thinking…")

    def _handle_result(self, event):
        for index in list(self._stream_blocks):
            entry = self._stream_blocks[index]
            entry[0].set_text(entry[1])
        self._stream_blocks = {}
        for tool in self._tools.values():
            tool.cancel()
        if event.get("is_error") or event.get("subtype") not in (None, "success"):
            errors = event.get("errors") or []
            body = "\n".join(errors) if errors else str(event.get("result") or event.get("subtype"))
            self._add_notice("Claude Code reported an error", body, error=True)
        self._set_busy(False)

    def _handle_control_request(self, event):
        request = event.get("request") or {}
        if request.get("subtype") != "can_use_tool":
            if self.process is not None:
                self.process.reject_control(event.get("request_id"), f"Unsupported request: {request.get('subtype')}")
            return
        request = {**request, "request_id": event.get("request_id")}
        card = _PermissionCard(request, self.describer, self._respond_permission, self._on_plan_approved)
        self._permission_cards[request["request_id"]] = card
        self.working.set_visible(False)
        self._stick_to_bottom = True
        self._append(card)

    def _handle_control_cancel_request(self, event):
        card = self._permission_cards.pop(event.get("request_id"), None)
        if card is not None:
            card.resolve("Cancelled", allowed=False)

    def _tool(self, tool_id, name):
        tool = self._tools.get(tool_id)
        if tool is None:
            tool = _ToolCall(name, self.describer)
            self._tools[tool_id] = tool
            self._append(tool)
        return tool



def _clamp(child):
    clamp = Adw.Clamp(child=child, maximum_size=760, tightening_threshold=600)
    clamp.add_css_class("chat-clamp")
    return clamp
