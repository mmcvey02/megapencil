"""Rectangle, Ellipse and Line tools."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPen

from ... import commands as C
from ...model.geometry import constrain_angle
from ...model.items import EllipseItem, Item, LineItem, RectItem
from ...model.paint import BLACK
from ..qtbridge import qtransform, to_qpath
from .base import ACCENT, Tool

MIN_DRAG = 3.0  # view pixels


def drag_box(p0: QPointF, p1: QPointF, square: bool, centered: bool) -> tuple[float, float, float, float]:
    """Box (x, y, w, h) for a drag from p0 to p1 with Shift / Alt behaviour."""
    dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
    if square:
        m = max(abs(dx), abs(dy))
        dx = m if dx >= 0 else -m
        dy = m if dy >= 0 else -m
    if centered:
        return p0.x() - abs(dx), p0.y() - abs(dy), 2 * abs(dx), 2 * abs(dy)
    return min(p0.x(), p0.x() + dx), min(p0.y(), p0.y() + dy), abs(dx), abs(dy)


class ShapeTool(Tool):
    cursor = Qt.CrossCursor

    def __init__(self, window):
        super().__init__(window)
        self._start: QPointF | None = None
        self._preview: Item | None = None

    def make(self, p0: QPointF, p1: QPointF, mods) -> Item | None:
        raise NotImplementedError

    def _style(self, item: Item) -> Item:
        st = self.window.state
        item.fill, item.stroke, item.stroke_width = st.fill, st.stroke, st.stroke_width
        return item

    def mouse_press(self, view, ev, pos):
        self._preview = None
        self._start = pos if self.target_layer(view) else None

    def mouse_move(self, view, ev, pos):
        if self._start is None:
            return
        far = (view.to_view(pos) - view.to_view(self._start)).manhattanLength() >= MIN_DRAG
        self._preview = self.make(self._start, pos, ev.modifiers()) if far else None
        view.refresh()

    def mouse_release(self, view, ev, pos):
        if self._start is None:
            return
        self.mouse_move(view, ev, pos)
        item, self._preview, self._start = self._preview, None, None
        layer = self.target_layer(view)
        if item is None or layer is None:
            return
        tab = view.tab
        tab.push(C.add_items(tab.doc, layer, [item], f"Draw {self.label}"))
        tab.scene.set_selection([item])

    def key_press(self, view, ev) -> bool:
        if ev.key() == Qt.Key_Escape and self._start is not None:
            self._start = self._preview = None
            return True
        return False

    def paint(self, view, painter):
        if self._preview is not None:
            path = (qtransform(self._preview.transform) * view.viewportTransform()).map(
                to_qpath(self._preview.local_path()))
            painter.setPen(QPen(ACCENT, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)


class RectTool(ShapeTool):
    name, label, shortcut, icon = "rect", "Rectangle", "M", "rect"

    def make(self, p0, p1, mods):
        x, y, w, h = drag_box(p0, p1, bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier))
        if w <= 0 or h <= 0:
            return None
        return self._style(RectItem(x=x, y=y, w=w, h=h, rx=min(self.window.state.corner_radius, w / 2, h / 2)))


class EllipseTool(ShapeTool):
    name, label, shortcut, icon = "ellipse", "Ellipse", "L", "ellipse"

    def make(self, p0, p1, mods):
        x, y, w, h = drag_box(p0, p1, bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier))
        if w <= 0 or h <= 0:
            return None
        return self._style(EllipseItem(cx=x + w / 2, cy=y + h / 2, rx=w / 2, ry=h / 2))


class LineTool(ShapeTool):
    name, label, shortcut, icon = "line", "Line", "\\", "line"

    def make(self, p0, p1, mods):
        dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
        if mods & Qt.ShiftModifier:
            dx, dy = constrain_angle(dx, dy, 45.0)
        x0, y0 = p0.x(), p0.y()
        if mods & Qt.AltModifier:
            x0, y0 = x0 - dx, y0 - dy
        st = self.window.state
        return LineItem(x1=x0, y1=y0, x2=p0.x() + dx, y2=p0.y() + dy, fill=None,
                        stroke=st.stroke if st.stroke is not None else BLACK, stroke_width=st.stroke_width)
