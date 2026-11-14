"""Periodic autosave of modified documents and crash recovery."""
from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import QObject, QTimer

from ..model import svgio
from ..settings import data_dir


def autosave_dir() -> str:
    d = os.path.join(data_dir(), "autosave")
    os.makedirs(d, exist_ok=True)
    return d


class AutosaveManager(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.run)
        self.configure()

    def configure(self) -> None:
        s = self.window.settings
        self.timer.stop()
        if s.get("autosave_enabled"):
            self.timer.start(max(10, s.get("autosave_interval")) * 1000)

    def _files(self, tab) -> tuple[str, str]:
        base = os.path.join(autosave_dir(), tab.autosave_id)
        return base + ".svg", base + ".json"

    def run(self) -> int:
        """Write autosave copies of modified documents; returns how many were written."""
        n = 0
        for tab in self.window.tabs():
            if tab.autosave_dirty and tab.is_modified():
                svg, meta = self._files(tab)
                try:
                    tmp = svg + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(svgio.dumps(tab.doc))
                    os.replace(tmp, svg)
                    with open(meta, "w", encoding="utf-8") as f:
                        json.dump({"path": tab.path, "name": tab.name(), "time": time.time()}, f)
                    tab.autosave_dirty = False
                    n += 1
                except OSError:
                    pass
        return n

    def discard(self, tab) -> None:
        for f in self._files(tab):
            try:
                os.remove(f)
            except OSError:
                pass

    # -- recovery -----------------------------------------------------
    @staticmethod
    def pending() -> list[dict]:
        out = []
        d = autosave_dir()
        for name in sorted(os.listdir(d)):
            if name.endswith(".json"):
                svg = os.path.join(d, name[:-5] + ".svg")
                try:
                    with open(os.path.join(d, name), encoding="utf-8") as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    continue
                if os.path.exists(svg):
                    meta["svg"] = svg
                    meta["meta"] = os.path.join(d, name)
                    out.append(meta)
        return out

    @staticmethod
    def remove_pending(entry: dict) -> None:
        for f in (entry.get("svg"), entry.get("meta")):
            try:
                os.remove(f)
            except (OSError, TypeError):
                pass
