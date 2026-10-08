"""Runs `claude` in headless stream-json mode and speaks its line-delimited
JSON protocol: user messages and control requests go in on stdin, and
assistant/tool/result events plus permission requests come out on stdout."""

import json
import os
import uuid

from gi.repository import Gio, GLib

# Markers a parent Claude Code session sets; inheriting them would make the
# child think it's nested inside another session.
_NESTED_SESSION_VARS = ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID")


class ClaudeProcess:
    def __init__(self, folder, on_event, on_exit, model=None, permission_mode="default", resume=None):
        self.folder = folder
        self._on_event = on_event
        self._on_exit = on_exit
        self._stderr = []
        self._cancellable = Gio.Cancellable()

        executable = find_claude()
        if executable is None:
            raise FileNotFoundError("Couldn't find the claude command on your PATH.")

        argv = [
            executable,
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--permission-prompt-tool", "stdio",
            "--permission-mode", permission_mode,
            "--allow-dangerously-skip-permissions",
        ]
        if model:
            argv += ["--model", model]
        if resume:
            argv += ["--resume", resume]

        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDIN_PIPE
            | Gio.SubprocessFlags.STDOUT_PIPE
            | Gio.SubprocessFlags.STDERR_PIPE
        )
        launcher.set_cwd(folder)
        for name in _NESTED_SESSION_VARS:
            launcher.unsetenv(name)

        self._process = launcher.spawnv(argv)
        self._stdin = self._process.get_stdin_pipe()
        self._stdout = Gio.DataInputStream.new(self._process.get_stdout_pipe())
        self._stderr_stream = Gio.DataInputStream.new(self._process.get_stderr_pipe())

        self._read_stdout()
        self._read_stderr()
        self._process.wait_async(None, self._on_wait)

        self.control("initialize", hooks=None)

    # -- Sending --------------------------------------------------------------

    def _write(self, obj):
        if self._stdin is None:
            return
        data = (json.dumps(obj) + "\n").encode()
        try:
            self._stdin.write_all(data, None)
            self._stdin.flush(None)
        except GLib.Error:
            self._stdin = None

    def send_user_message(self, text):
        self._write({
            "type": "user",
            "message": {"role": "user", "content": text},
            "parent_tool_use_id": None,
            "session_id": "",
        })

    def control(self, subtype, **fields):
        self._write({
            "type": "control_request",
            "request_id": f"req-{uuid.uuid4()}",
            "request": {"subtype": subtype, **fields},
        })

    def interrupt(self):
        self.control("interrupt")

    def set_permission_mode(self, mode):
        self.control("set_permission_mode", mode=mode)

    def set_model(self, model):
        self.control("set_model", model=model)

    def respond_permission(self, request_id, allow, updated_input=None, updated_permissions=None, message=None):
        if allow:
            response = {"behavior": "allow", "updatedInput": updated_input or {}}
            if updated_permissions:
                response["updatedPermissions"] = updated_permissions
        else:
            response = {"behavior": "deny", "message": message or "The user denied this request."}
        self._write({
            "type": "control_response",
            "response": {"subtype": "success", "request_id": request_id, "response": response},
        })

    def reject_control(self, request_id, error):
        self._write({
            "type": "control_response",
            "response": {"subtype": "error", "request_id": request_id, "error": error},
        })

    def stop(self):
        self._cancellable.cancel()
        if self._stdin is not None:
            try:
                self._stdin.close(None)
            except GLib.Error:
                pass
            self._stdin = None
        self._process.force_exit()

    # -- Receiving ------------------------------------------------------------

    def _read_stdout(self):
        self._stdout.read_line_async(GLib.PRIORITY_DEFAULT, self._cancellable, self._on_stdout_line)

    def _on_stdout_line(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return
        if line is None:
            return  # EOF; _on_wait reports the exit
        line = line.strip()
        if line:
            try:
                event = json.loads(line)
            except ValueError:
                event = None
            if isinstance(event, dict):
                self._on_event(event)
        self._read_stdout()

    def _read_stderr(self):
        self._stderr_stream.read_line_async(GLib.PRIORITY_DEFAULT, self._cancellable, self._on_stderr_line)

    def _on_stderr_line(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return
        if line is None:
            return
        self._stderr.append(line)
        del self._stderr[:-40]
        self._read_stderr()

    def _on_wait(self, process, result):
        try:
            process.wait_finish(result)
        except GLib.Error:
            pass
        if self._cancellable.is_cancelled():
            return
        # Let the stderr reader drain before reporting why it exited.
        GLib.timeout_add(150, self._report_exit)

    def _report_exit(self):
        status = self._process.get_exit_status() if self._process.get_if_exited() else -1
        self._on_exit(status, "\n".join(self._stderr).strip())
        return GLib.SOURCE_REMOVE



def find_claude():
    """Locate the claude executable. Desktop launchers often start apps with a
    PATH that lacks ~/.local/bin, where the native installer puts it."""
    found = GLib.find_program_in_path("claude")
    if found:
        return found
    for candidate in ("~/.local/bin/claude", "~/.claude/local/claude", "/usr/local/bin/claude"):
        path = os.path.expanduser(candidate)
        if os.access(path, os.X_OK):
            return path
    return None
