"""Stroke panel: weight, cap, join, dashes."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget

from ..widgets import set_quiet, spin

CAPS = ["butt", "round", "square"]
JOINS = ["miter", "round", "bevel"]


def parse_dash(text: str) -> tuple[float, ...] | None:
    """'4 2' or '4, 2' -> (4.0, 2.0); empty -> (); invalid -> None."""
    parts = [p for p in text.replace(",", " ").split() if p]
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError:
        return None
    if any(v < 0 for v in vals) or (vals and not any(v > 0 for v in vals)):
        return None
    return vals


class StrokePanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        form = QFormLayout(self)
        self.weight = spin(0, 1000, 0.5, 2, " px", 100)
        self.weight.valueChanged.connect(lambda v: window.apply_style("stroke_width", v, text="Stroke Width"))
        self.cap = QComboBox()
        self.cap.addItems([c.capitalize() for c in CAPS])
        self.cap.currentIndexChanged.connect(lambda i: window.apply_style("stroke_cap", CAPS[i], text="Stroke Cap"))
        self.join = QComboBox()
        self.join.addItems([j.capitalize() for j in JOINS])
        self.join.currentIndexChanged.connect(lambda i: window.apply_style("stroke_join", JOINS[i], text="Stroke Join"))
        self.dash = QLineEdit()
        self.dash.setPlaceholderText("solid — e.g. 8 4 for dashes")
        self.dash.editingFinished.connect(self._dash_edited)
        form.addRow("Weight:", self.weight)
        form.addRow("Cap:", self.cap)
        form.addRow("Corner:", self.join)
        form.addRow("Dashes:", self.dash)
        window.contextChanged.connect(self.refresh)

    def _dash_edited(self) -> None:
        vals = parse_dash(self.dash.text())
        if vals is None:
            self.window.status_message("Dashes must be a list of positive numbers, e.g. 8 4")
            self.refresh()
            return
        self.window.apply_style("dash", vals, text="Dashes")

    def refresh(self) -> None:
        leaves = self.window.selection_leaves()
        first = leaves[0] if leaves else None
        set_quiet(self.weight, self.window.state.stroke_width)
        for combo, values, attr in ((self.cap, CAPS, "stroke_cap"), (self.join, JOINS, "stroke_join")):
            combo.blockSignals(True)
            combo.setCurrentIndex(values.index(getattr(first, attr)) if first else 0)
            combo.blockSignals(False)
        if not self.dash.hasFocus():
            set_quiet(self.dash, " ".join(f"{v:g}" for v in first.dash) if first else "")
