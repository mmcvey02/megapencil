"""Hand and Zoom tools."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen

from .base import Tool


class HandTool(Tool):
    name, label, shortcut, icon = "hand", "Hand", "H", "hand"
    cursor = Qt.OpenHandCursor

    def __init__(self, window):
        super().__init__(window)
        self._last = None

    def mouse_press(self, view, ev, pos):
        self._last = ev.position()
        view.viewport().setCursor(Qt.ClosedHandCursor)

    def mouse_move(self, view, ev, pos):
        if self._last is not None:
            d = ev.position() - self._last
            self._last = ev.position()
            view.pan_by(d.x(), d.y())

    def mouse_release(self, view, ev, pos):
        self._last = None
        view.viewport().setCursor(self.cursor)


class ZoomTool(Tool):
    name, label, shortcut, icon = "zoom", "Zoom", "Z", "zoom"
    cursor = Qt.CrossCursor

    def __init__(self, window):
        super().__init__(window)
        self._start: QPointF | None = None
        self._cur: QPointF | None = None

    def mouse_press(self, view, ev, pos):
        self._start = self._cur = pos

    def mouse_move(self, view, ev, pos):
        if self._start is not None:
            self._cur = pos
            view.refresh()

    def mouse_release(self, view, ev, pos):
        if self._start is None:
            return
        rect = QRectF(self._start, pos).normalized()
        self._start = self._cur = None
        if rect.width() * view.zoom > 6 and rect.height() * view.zoom > 6:
            view.zoom_to_rect(rect)
        else:
            factor = 1 / 1.5 if ev.modifiers() & Qt.AltModifier else 1.5
            view.set_zoom(view.zoom * factor, ev.position())
        view.refresh()

    def paint(self, view, painter):
        if self._start is not None and self._cur is not None:
            r = QRectF(view.to_view(self._start), view.to_view(self._cur)).normalized()
            painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)
