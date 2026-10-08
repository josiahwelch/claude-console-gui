"""Persisted list of recently used project folders."""

import json
import os
from pathlib import Path

from gi.repository import GLib

_MAX_RECENTS = 8


def _path():
    return Path(GLib.get_user_config_dir()) / "claude-console-gui" / "recents.json"


def load():
    try:
        folders = json.loads(_path().read_text())
    except (OSError, ValueError):
        return []
    return [f for f in folders if isinstance(f, str) and os.path.isdir(f)]


def add(folder):
    folders = [folder] + [f for f in load() if f != folder]
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(folders[:_MAX_RECENTS]))
    except OSError:
        pass
