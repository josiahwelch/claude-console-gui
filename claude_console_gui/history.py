"""Reads Claude Code's saved conversations from ~/.claude/projects so past
sessions can be listed and resumed."""

import glob
import itertools
import json
import os
import re
import threading
import time
from dataclasses import dataclass

from gi.repository import GLib

# Only the start and end of each transcript are read to build the list: the
# folder and first prompt are near the top, the latest title near the bottom.
_HEAD_BYTES = 64 * 1024
_TAIL_BYTES = 64 * 1024

_COMMAND_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


@dataclass
class HistoryEntry:
    session_id: str
    path: str
    folder: str
    title: str
    modified: float


def projects_dir():
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(config, "projects")


def prompt_text(entry):
    """The text the user typed for a transcript "user" entry, or None for
    tool results, injected context, and other non-prompt entries."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return None
    if entry.get("isSidechain"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        return None
    text = content.strip()
    if text.startswith("<"):
        # Slash commands are stored as <command-name>/x</command-name> markup;
        # other tagged text is context the CLI injected, not something typed.
        name = _COMMAND_NAME.search(text)
        if not name:
            return None
        args = _COMMAND_ARGS.search(text)
        return f"{name.group(1).strip()} {args.group(1).strip() if args else ''}".strip()
    return text


def _json_lines(data, skip_partial_first=False):
    lines = data.split(b"\n")
    if skip_partial_first:
        lines = lines[1:]
    for line in lines:
        try:
            yield json.loads(line)
        except ValueError:
            continue


def _read_entry(path, modified):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(_HEAD_BYTES)
            tail = b""
            if size > _HEAD_BYTES:
                f.seek(max(_HEAD_BYTES, size - _TAIL_BYTES))
                tail = f.read()
    except OSError:
        return None

    folder = None
    first_prompt = None
    for obj in _json_lines(head):
        if folder is None and obj.get("cwd"):
            folder = obj["cwd"]
        if first_prompt is None:
            first_prompt = prompt_text(obj)
        if folder and first_prompt:
            break

    # Later records win, so walk the head then the tail in file order.
    custom_title = ai_title = last_prompt = None
    records = itertools.chain(_json_lines(head), _json_lines(tail, skip_partial_first=True))
    for obj in records:
        kind = obj.get("type")
        if kind == "custom-title" and obj.get("customTitle"):
            custom_title = obj["customTitle"]
        elif kind == "ai-title" and obj.get("aiTitle"):
            ai_title = obj["aiTitle"]
        elif kind == "last-prompt" and obj.get("lastPrompt"):
            last_prompt = obj["lastPrompt"]
        elif kind == "relocated" and obj.get("relocatedCwd"):
            folder = obj["relocatedCwd"]

    if not (first_prompt or last_prompt) or not folder:
        return None  # empty session, or a subagent/sidechain-only file
    title = custom_title or ai_title or first_prompt or last_prompt
    title = " ".join(title.split())
    return HistoryEntry(
        session_id=os.path.splitext(os.path.basename(path))[0],
        path=path,
        folder=folder,
        title=title[:120],
        modified=modified,
    )


class History:
    """Scans saved transcripts on a worker thread, caching parsed entries by
    modification time so rescans only re-read files that changed."""

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
        self._scanning = False

    def scan_async(self, callback):
        with self._lock:
            if self._scanning:
                return
            self._scanning = True
        threading.Thread(target=self._scan, args=(callback,), daemon=True).start()

    def _scan(self, callback):
        entries = []
        try:
            for path in glob.glob(os.path.join(projects_dir(), "*", "*.jsonl")):
                try:
                    modified = os.path.getmtime(path)
                except OSError:
                    continue
                cached = self._cache.get(path)
                if cached is None or cached[0] != modified:
                    cached = (modified, _read_entry(path, modified))
                    self._cache[path] = cached
                if cached[1] is not None:
                    entries.append(cached[1])
            entries.sort(key=lambda e: e.modified, reverse=True)
        finally:
            with self._lock:
                self._scanning = False
        GLib.idle_add(lambda: (callback(entries), GLib.SOURCE_REMOVE)[1])


def load_transcript(path):
    """Every parseable entry in a saved transcript, in file order."""
    entries = []
    try:
        with open(path, "rb") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return entries


def relative_time(timestamp):
    seconds = time.time() - timestamp
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if seconds < 7 * 86400:
        return f"{int(seconds // 86400)}d ago"
    then = time.localtime(timestamp)
    day = f"{time.strftime('%b', then)} {then.tm_mday}"
    if then.tm_year == time.localtime().tm_year:
        return day
    return f"{day}, {then.tm_year}"
