"""Rulers along the top and left of the canvas; drag out of them to make guides."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme

RULER_SIZE = 20


def tick_step(zoom: float, min_px: float = 60.0) -> float:
    """Smallest 1/2/5 x 10^n step that is at least ``min_px`` pixels wide."""
    raw = min_px / zoom
    exp = math.floor(math.log10(raw)) if raw > 0 else 0
    for m in (1, 2, 5, 10):
        step = m * 10 ** exp
        if step >= raw:
            return step
    return 10 ** (exp + 1)


class Ruler(QWidget):
    def __init__(self, view, orient: str):
        super().__init__()
        self.view = view
        self.orient = orient  # "h" (top) or "v" (left)
        self.cursor_pos: float | None = None
        if orient == "h":
            self.setFixedHeight(RULER_SIZE)
        else:
            self.setFixedWidth(RULER_SIZE)
        self.setCursor(Qt.SplitVCursor if orient == "h" else Qt.SplitHCursor)
        self.setToolTip("Drag onto the canvas to create a guide")
        view.zoomChanged.connect(lambda _z: self.update())
        view.cursorMoved.connect(self._cursor)

    def _cursor(self, pos: QPointF) -> None:
        self.cursor_pos = pos.x() if self.orient == "h" else pos.y()
        self.update()

    def paintEvent(self, ev) -> None:
        t = theme.current()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t["alt"]))
        horizontal = self.orient == "h"
        length = self.width() if horizontal else self.height()
        zoom = self.view.zoom
        origin = self.view.to_scene(QPointF(0, 0))
        start = origin.x() if horizontal else origin.y()
        step = tick_step(zoom)
        minor = step / 10
        f = QFont(self.font())
        f.setPixelSize(9)
        p.setFont(f)
        p.setPen(QPen(QColor(t["disabled"]), 1))
        i = math.floor(start / minor)
        while True:
            val = i * minor
            px = (val - start) * zoom
            if px > length:
                break
            i += 1
            if px < 0:
                continue
            major = (i - 1) % 10 == 0
            size = RULER_SIZE if major else (8 if (i - 1) % 5 == 0 else 4)
            if horizontal:
                p.drawLine(int(px), RULER_SIZE - size, int(px), RULER_SIZE)
            else:
                p.drawLine(RULER_SIZE - size, int(px), RULER_SIZE, int(px))
            if major:
                label = f"{val:g}" if abs(step) < 1 else str(int(round(val)))
                p.setPen(QColor(t["text"]))
                if horizontal:
                    p.drawText(int(px) + 3, 10, label)
                else:
                    p.save()
                    p.translate(10, int(px) + 3)
                    p.rotate(90)
                    p.drawText(0, 0, label)
                    p.restore()
                p.setPen(QPen(QColor(t["disabled"]), 1))
        if self.cursor_pos is not None:
            px = (self.cursor_pos - start) * zoom
            p.setPen(QPen(QColor(t["highlight"]), 1))
            if horizontal:
                p.drawLine(int(px), 0, int(px), RULER_SIZE)
            else:
                p.drawLine(0, int(px), RULER_SIZE, int(px))
        p.end()

    # -- guide creation -----------------------------------------------
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.view.guides_visible = True
            self.view.begin_guide_drag(self.orient)

    def mouseMoveEvent(self, ev) -> None:
        if self.view.guide_drag is not None:
            vp = self.view.viewport().mapFromGlobal(ev.globalPosition().toPoint())
            self.view.update_guide_drag(QPointF(vp))

    def mouseReleaseEvent(self, ev) -> None:
        if self.view.guide_drag is not None:
            vp = self.view.viewport().mapFromGlobal(ev.globalPosition().toPoint())
            self.view.update_guide_drag(QPointF(vp))
            self.view.finish_guide_drag()
