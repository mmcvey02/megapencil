"""Pen tool: click for corner points, drag for smooth points."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from ... import commands as C
from ...model.geometry import constrain_angle
from ...model.items import PathItem
from ...model.path import Anchor, PathData, SubPath
from ..qtbridge import to_qpath
from .base import ACCENT
from .pathedit import HIT, AnchorTool, commit_path


class PenTool(AnchorTool):
    name, label, shortcut, icon = "pen", "Pen", "P", "pen"
    cursor = Qt.CrossCursor

    def __init__(self, window):
        super().__init__(window)
        self._clear()

    def _clear(self) -> None:
        self.anchors: list[Anchor] = []  # document coordinates
        self.closed = False
        self.dragging: int | str | None = None  # anchor index, or "close"
        self.cursor_pos: QPointF | None = None
        self.continuing = None  # (item, subpath index)

    def in_progress(self) -> bool:
        return bool(self.anchors)

    def deactivate(self, view) -> None:
        self.commit(view)

    # -- mouse --------------------------------------------------------
    def _near(self, view, a: Anchor, vpos: QPointF) -> bool:
        p = view.to_view(QPointF(a.x, a.y))
        return max(abs(p.x() - vpos.x()), abs(p.y() - vpos.y())) <= HIT

    def _try_continue(self, view, vpos: QPointF) -> bool:
        """Start from an end point of a selected open path."""
        for it in self.targets(view):
            path = it.local_path()
            t = it.world_transform()
            for si, s in enumerate(path.subpaths):
                if s.closed or len(s.anchors) < 2:
                    continue
                world = [a.transformed(t) for a in s.anchors]
                if self._near(view, world[-1], vpos):
                    self.anchors = world
                elif self._near(view, world[0], vpos):
                    self.anchors = SubPath(world).reversed().anchors
                else:
                    continue
                self.continuing = (it, si)
                self.dragging = len(self.anchors) - 1
                return True
        return False

    def mouse_press(self, view, ev, pos):
        vpos = ev.position()
        if not self.anchors:
            if self._try_continue(view, vpos):
                return
            if self.target_layer(view) is None:
                return
        elif len(self.anchors) >= 2 and self._near(view, self.anchors[0], vpos):
            self.closed = True
            self.dragging = "close"
            return
        x, y = pos.x(), pos.y()
        if self.anchors and ev.modifiers() & Qt.ShiftModifier:
            last = self.anchors[-1]
            dx, dy = constrain_angle(x - last.x, y - last.y, 45.0)
            x, y = last.x + dx, last.y + dy
        self.anchors.append(Anchor(x, y))
        self.dragging = len(self.anchors) - 1

    def mouse_move(self, view, ev, pos):
        self.cursor_pos = pos
        if self.dragging is not None:
            a = self.anchors[0] if self.dragging == "close" else self.anchors[self.dragging]
            dx, dy = pos.x() - a.x, pos.y() - a.y
            if ev.modifiers() & Qt.ShiftModifier:
                dx, dy = constrain_angle(dx, dy, 45.0)
            if (abs(dx) + abs(dy)) * view.zoom >= 3:
                a.hin = (a.x - dx, a.y - dy)
                a.smooth = True
                if self.dragging != "close":
                    a.hout = (a.x + dx, a.y + dy)
                elif a.hout is None:
                    a.smooth = False
        if self.anchors:
            view.refresh()

    def mouse_release(self, view, ev, pos):
        self.dragging = None
        if self.closed:
            self.commit(view)

    def double_click(self, view, ev, pos):
        if len(self.anchors) >= 2:
            a, b = self.anchors[-1], self.anchors[-2]
            if abs(a.x - b.x) * view.zoom < 2 and abs(a.y - b.y) * view.zoom < 2:
                self.anchors.pop()
        self.dragging = None
        self.commit(view)

    # -- keys ---------------------------------------------------------
    def key_press(self, view, ev) -> bool:
        if not self.anchors:
            return False
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.commit(view)
            return True
        return False

    def undo_step(self, view) -> bool:
        if not self.anchors or self.dragging is not None:
            return False
        self.anchors.pop()
        if self.anchors:
            self.anchors[-1].hout = None if not self.anchors[-1].smooth else self.anchors[-1].hout
        elif self.continuing:
            self._clear()
        return True

    def delete_pressed(self, view) -> bool:
        return self.undo_step(view)

    # -- commit -------------------------------------------------------
    def commit(self, view) -> None:
        anchors, closed, cont = self.anchors, self.closed, self.continuing
        self._clear()
        tab = view.tab
        if len(anchors) < 2:
            view.refresh()
            return
        if not closed:
            anchors[0].hin = None
            anchors[-1].hout = None
        sub = SubPath([a.copy() for a in anchors], closed)
        if cont is not None and tab.doc.contains(cont[0]):
            it, si = cont
            inv = it.world_transform().inverted()
            path = it.local_path().copy()
            path.subpaths[si] = SubPath([a.transformed(inv) for a in sub.anchors], closed)
            commit_path(tab, it, path, "Pen")
        else:
            layer = self.target_layer(view)
            if layer is None:
                return
            st = self.window.state
            item = PathItem(path=PathData([sub]), fill=st.fill, stroke=st.stroke, stroke_width=st.stroke_width)
            tab.push(C.add_items(tab.doc, layer, [item], "Pen"))
            tab.scene.set_selection([item])
        view.refresh()

    # -- overlay ------------------------------------------------------
    def paint(self, view, painter):
        if not self.anchors:
            self.draw_anchors(view, painter, with_handles=False)
            return
        vt = view.viewportTransform()
        painter.setPen(QPen(ACCENT, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(vt.map(to_qpath(PathData([SubPath(self.anchors, self.closed)]))))
        last = self.anchors[-1]
        if self.cursor_pos is not None and self.dragging is None and not self.closed:
            rubber = QPainterPath()
            rubber.moveTo(last.x, last.y)
            if last.hout:
                c = self.cursor_pos
                rubber.cubicTo(last.hout[0], last.hout[1], c.x(), c.y(), c.x(), c.y())
            else:
                rubber.lineTo(self.cursor_pos)
            painter.setPen(QPen(ACCENT, 1, Qt.DashLine))
            painter.drawPath(vt.map(rubber))
        painter.setPen(QPen(ACCENT, 1))
        shown = self.anchors[0] if self.dragging == "close" else last
        for h in (shown.hin, shown.hout):
            if h is not None:
                hp = vt.map(QPointF(*h))
                painter.drawLine(vt.map(QPointF(shown.x, shown.y)), hp)
                painter.setBrush(ACCENT)
                painter.drawEllipse(hp, 3, 3)
        for i, a in enumerate(self.anchors):
            painter.setBrush(ACCENT if a is last else QColor("white"))
            painter.drawRect(self.handle_rect(vt.map(QPointF(a.x, a.y)), 7 if i == 0 else 6))
