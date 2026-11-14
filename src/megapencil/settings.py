"""Persistent preferences (QSettings; stored locally, no network)."""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings, QStandardPaths

DEFAULTS = {
    "theme": "dark",
    "autosave_enabled": True,
    "autosave_interval": 120,  # seconds
    "nudge": 1.0,
    "big_nudge": 10.0,
    "default_width": 800,
    "default_height": 600,
    "show_rulers": True,
    "max_recent": 10,
    "install_prompted": False,
}


class Settings:
    def __init__(self):
        self.qs = QSettings("MegaPencil", "MegaPencil")

    def get(self, key: str):
        default = DEFAULTS[key]
        v = self.qs.value(key, default)
        if isinstance(default, bool):
            return v in (True, "true", "1", 1)
        try:
            return type(default)(v)
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value) -> None:
        self.qs.setValue(key, value)

    def recent_files(self) -> list[str]:
        v = self.qs.value("recent_files", [])
        if isinstance(v, str):
            v = [v]
        return [p for p in (v or []) if isinstance(p, str)]

    def add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        files = [p for p in self.recent_files() if p != path]
        files.insert(0, path)
        self.qs.setValue("recent_files", files[: self.get("max_recent")])

    def clear_recent(self) -> None:
        self.qs.setValue("recent_files", [])


def data_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.expanduser("~/.megapencil")
    os.makedirs(base, exist_ok=True)
    return base
