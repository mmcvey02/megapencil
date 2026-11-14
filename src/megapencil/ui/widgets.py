"""Small shared widgets."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QDoubleSpinBox, QToolButton, QWidget

from ..model.paint import Gradient
from .icons import swatch_pixmap
from .qtbridge import make_brush


def paint_icon(paint, size: int = 18) -> QIcon:
    if paint is None:
        return QIcon(swatch_pixmap(None, size, none=True))
    return QIcon(swatch_pixmap(make_brush(paint, QRectF(0, 0, size, size)), size))


def paint_label(paint) -> str:
    if paint is None:
        return "None"
    if isinstance(paint, Gradient):
        return f"{paint.kind.capitalize()} gradient"
    return paint.to_hex().upper()


class PaintButton(QToolButton):
    """Button showing a paint swatch."""

    def __init__(self, tooltip: str = ""):
        super().__init__()
        self.setIconSize(QSize(18, 18))
        self.setToolTip(tooltip)
        self.set_paint(None)

    def set_paint(self, paint) -> None:
        self.setIcon(paint_icon(paint))


def spin(lo: float, hi: float, step: float = 1.0, decimals: int = 2, suffix: str = "", width: int = 76) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    s.setFixedWidth(width)
    return s


def set_quiet(widget, value) -> None:
    """Set a widget value without emitting change signals."""
    widget.blockSignals(True)
    try:
        if hasattr(widget, "setValue"):
            widget.setValue(value)
        elif hasattr(widget, "setCurrentText"):
            widget.setCurrentText(value)
        elif hasattr(widget, "setChecked"):
            widget.setChecked(value)
        elif hasattr(widget, "setText"):
            widget.setText(value)
    finally:
        widget.blockSignals(False)


class FillStrokeSwatch(QWidget):
    """Overlapping fill / stroke squares.  Click to target, double-click to edit."""

    targetClicked = Signal(str)
    editRequested = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setFixedSize(58, 58)
        self.setToolTip("Fill (front) and Stroke.  Click to select, double-click to edit.\n"
                        "Shift+X swaps, D resets to default.")
        state.changed.connect(self.update)

    def _rects(self):
        return QRectF(4, 4, 30, 30), QRectF(22, 22, 30, 30)  # fill, stroke

    def _hit(self, pos) -> str | None:
        fill, stroke = self._rects()
        order = [("fill", fill), ("stroke", stroke)] if self.state.target == "fill" else [("stroke", stroke), ("fill", fill)]
        for name, r in order:
            if r.contains(pos):
                return name
        return None

    def mousePressEvent(self, ev) -> None:
        name = self._hit(ev.position())
        if name:
            self.targetClicked.emit(name)

    def mouseDoubleClickEvent(self, ev) -> None:
        name = self._hit(ev.position())
        if name:
            self.editRequested.emit(name)

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fill, stroke = self._rects()

        def draw_fill():
            self._square(p, fill, self.state.fill)

        def draw_stroke():
            self._square(p, stroke, self.state.stroke, hollow=True)

        for fn in ((draw_stroke, draw_fill) if self.state.target == "fill" else (draw_fill, draw_stroke)):
            fn()
        p.end()

    def _square(self, p, r, paint, hollow=False) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRect(r)
        if paint is None:
            p.setPen(QPen(QColor("#e02020"), 2))
            p.drawLine(r.bottomLeft(), r.topRight())
        else:
            p.setBrush(make_brush(paint, r))
            p.setPen(Qt.NoPen)
            p.drawRect(r)
        if hollow:
            inner = r.adjusted(8, 8, -8, -8)
            p.setPen(Qt.NoPen)
            p.setBrush(self.palette().window())
            p.drawRect(inner)
            p.setPen(QPen(QColor("#808080"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(inner)
        p.setPen(QPen(QColor("#808080"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
