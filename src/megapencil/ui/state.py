"""Application-wide drawing state (defaults for new objects)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..model.paint import BLACK, WHITE, Paint


class AppState(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.fill: Paint = WHITE
        self.stroke: Paint = BLACK
        self.stroke_width = 1.0
        self.corner_radius = 0.0
        self.font_family = "DejaVu Sans"
        self.font_size = 24.0
        self.target = "fill"  # which paint the Color panel edits

    def set(self, **kw) -> None:
        dirty = False
        for k, v in kw.items():
            if getattr(self, k) != v:
                setattr(self, k, v)
                dirty = True
        if dirty:
            self.changed.emit()

    def swap(self) -> None:
        self.fill, self.stroke = self.stroke, self.fill
        self.changed.emit()

    def reset_default(self) -> None:
        self.fill, self.stroke, self.stroke_width = WHITE, BLACK, 1.0
        self.changed.emit()
