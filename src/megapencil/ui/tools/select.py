"""Selection tool: click, marquee, move, scale, rotate, nudge."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPolygonF

from ... import commands as C
from ...model import ops
from ...model.geometry import Transform, constrain_angle
from ...model.items import TextItem
from ..qtbridge import qtransform
from .base import ACCENT, HANDLE, Tool

DRAG_START = 3.0  # view pixels before a press becomes a drag
ROTATE_OFFSET = 22.0  # view pixels above the top edge
# handle id -> (fx, fy) position on the selection rectangle
HANDLES = {"nw": (0, 0), "n": (0.5, 0), "ne": (1, 0), "e": (1, 0.5), "se": (1, 1), "s": (0.5, 1), "sw": (0, 1),
           "w": (0, 0.5)}
CURSORS = {"nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor, "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
           "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor, "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
           "rotate": Qt.PointingHandCursor}


def scale_transform(rect: QRectF, handle: str, pos: QPointF, uniform: bool, centered: bool) -> Transform:
    """Transform for dragging ``handle`` of ``rect`` to ``pos``."""
    fx, fy = HANDLES[handle]
    hx, hy = rect.x() + fx * rect.width(), rect.y() + fy * rect.height()
    if centered:
        ax, ay = rect.center().x(), rect.center().y()
    else:
        ax, ay = rect.x() + (1 - fx) * rect.width(), rect.y() + (1 - fy) * rect.height()

    def ratio(p, h, a):
        d = h - a
        if abs(d) < 1e-9:
            return 1.0
        r = (p - a) / d
        return r if abs(r) > 1e-4 else 1e-4

    sx = ratio(pos.x(), hx, ax) if fx != 0.5 else 1.0
    sy = ratio(pos.y(), hy, ay) if fy != 0.5 else 1.0
    if uniform:
        if fx == 0.5:
            sx = abs(sy)
        elif fy == 0.5:
            sy = abs(sx)
        else:
            m = max(abs(sx), abs(sy))
            sx, sy = math.copysign(m, sx), math.copysign(m, sy)
    return Transform.scaling(sx, sy, ax, ay)


class SelectTool(Tool):
    name, label, shortcut, icon = "select", "Selection", "V", "select"

    def __init__(self, window):
        super().__init__(window)
        self._reset()

    def _reset(self) -> None:
        self.mode: str | None = None  # move | marquee | scale | rotate | guide
        self.press: QPointF | None = None
        self.cur: QPointF | None = None
        self.dragging = False
        self.handle = ""
        self.rect0: QRectF | None = None
        self.transform: Transform | None = None
        self.clicked_item = None
        self.was_selected = False
        self.duplicate = False

    def deactivate(self, view) -> None:
        self._cancel(view)

    def _cancel(self, view) -> None:
        if self.mode in ("move", "scale", "rotate"):
            view.tab.scene.preview_transform(view.tab.scene.selection, None)
        if self.mode == "guide":
            view.guide_drag = None
        self._reset()

    # -- geometry -----------------------------------------------------
    def handle_points(self, view) -> dict[str, QPointF]:
        r = view.tab.scene.selection_rect()
        if r is None:
            return {}
        pts = {k: view.to_view(QPointF(r.x() + fx * r.width(), r.y() + fy * r.height()))
               for k, (fx, fy) in HANDLES.items()}
        top = pts["n"]
        pts["rotate"] = QPointF(top.x(), top.y() - ROTATE_OFFSET)
        return pts

    def handle_at(self, view, view_pos: QPointF) -> str:
        best, best_d = "", HANDLE
        for k, p in self.handle_points(view).items():
            d = max(abs(p.x() - view_pos.x()), abs(p.y() - view_pos.y()))
            if d <= best_d:
                best, best_d = k, d
        return best

    # -- mouse --------------------------------------------------------
    def mouse_press(self, view, ev, pos):
        scene = view.tab.scene
        self._reset()
        self.press = self.cur = pos
        vpos = ev.position()
        shift = bool(ev.modifiers() & Qt.ShiftModifier)
        h = self.handle_at(view, vpos) if scene.selection else ""
        if h:
            self.mode = "rotate" if h == "rotate" else "scale"
            self.handle = h
            self.rect0 = scene.selection_rect()
            return
        gi = view.guide_at(vpos)
        item = scene.item_at(pos, view.px(3))
        if item is None and gi is not None:
            self.mode = "guide"
            view.begin_guide_drag(view.tab.doc.guides[gi][0], gi)
            return
        if item is not None:
            self.clicked_item = item
            self.was_selected = item in scene.selection
            if shift and not self.was_selected:
                scene.set_selection(scene.selection + [item])
            elif not shift and not self.was_selected:
                scene.set_selection([item])
            if item in scene.selection:
                self.mode = "move"
                self.duplicate = bool(ev.modifiers() & Qt.AltModifier)
            return
        self.mode = "marquee"

    def mouse_move(self, view, ev, pos):
        if self.press is None or self.mode is None:
            h = self.handle_at(view, ev.position()) if view.tab.scene.selection else ""
            view.viewport().setCursor(CURSORS.get(h, self.cursor))
            return
        self.cur = pos
        scene = view.tab.scene
        if not self.dragging:
            if (view.to_view(pos) - view.to_view(self.press)).manhattanLength() < DRAG_START:
                return
            self.dragging = True
        mods = ev.modifiers()
        shift = bool(mods & Qt.ShiftModifier)
        if self.mode == "guide":
            view.update_guide_drag(ev.position())
            return
        if self.mode == "move":
            dx, dy = pos.x() - self.press.x(), pos.y() - self.press.y()
            if shift:
                dx, dy = constrain_angle(dx, dy, 45.0)
            self.transform = Transform.translation(dx, dy)
        elif self.mode == "scale":
            self.transform = scale_transform(self.rect0, self.handle, pos, shift, bool(mods & Qt.AltModifier))
        elif self.mode == "rotate":
            c = self.rect0.center()
            a0 = math.atan2(self.press.y() - c.y(), self.press.x() - c.x())
            a1 = math.atan2(pos.y() - c.y(), pos.x() - c.x())
            deg = math.degrees(a1 - a0)
            if shift:
                deg = round(deg / 15.0) * 15.0
            self.transform = Transform.rotation(deg, c.x(), c.y())
        if self.transform is not None:
            scene.preview_transform(scene.selection, qtransform(self.transform))
        view.refresh()

    def mouse_release(self, view, ev, pos):
        tab, scene = view.tab, view.tab.scene
        mode, dragging, t = self.mode, self.dragging, self.transform
        shift = bool(ev.modifiers() & Qt.ShiftModifier)
        if mode == "guide":
            if dragging:
                view.update_guide_drag(ev.position())
                view.finish_guide_drag()
            else:
                view.guide_drag = None
        elif mode in ("move", "scale", "rotate"):
            scene.preview_transform(scene.selection, None)
            if dragging and t is not None and not t.is_identity(1e-9):
                items = ops.top_level_only(scene.selection)
                if mode == "move" and self.duplicate:
                    self._duplicate(tab, items, t)
                else:
                    text = {"move": "Move", "scale": "Scale", "rotate": "Rotate"}[mode]
                    tab.push(C.transform_items(tab.doc, items, t, text))
            elif not dragging and mode == "move" and self.was_selected:
                if shift:  # shift-click on a selected object removes it
                    scene.set_selection([i for i in scene.selection if i is not self.clicked_item])
                elif len(scene.selection) > 1:
                    scene.set_selection([self.clicked_item])
        elif mode == "marquee":
            if dragging:
                found = scene.items_in_rect(QRectF(self.press, pos).normalized())
                scene.set_selection(scene.selection + [i for i in found if i not in scene.selection] if shift else found)
            elif not shift:
                scene.set_selection([])
        self._reset()

    def _duplicate(self, tab, items, t: Transform) -> None:
        cmds, clones = [], []
        for it in ops.doc_order(tab.doc, items):
            c = it.clone()
            c.parent = it.parent
            c.transform = ops.apply_world(c, t)
            clones.append(c)
            cmds.append(C.add_items(tab.doc, it.parent, [c]))
        tab.push(C.Macro("Duplicate", cmds))
        tab.scene.set_selection(clones)

    def double_click(self, view, ev, pos):
        item = view.tab.scene.item_at(pos, view.px(3), deep=True)
        self._cancel(view)
        if isinstance(item, TextItem) and "text" in self.window.tools:
            self.window.set_tool("text")
            self.window.tools["text"].edit_item(view, item)

    # -- keys ---------------------------------------------------------
    def key_press(self, view, ev) -> bool:
        tab, scene = view.tab, view.tab.scene
        key = ev.key()
        if key == Qt.Key_Escape:
            if self.mode:
                self._cancel(view)
            else:
                scene.set_selection([])
            return True
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if key in arrows and scene.selection and self.mode is None:
            s = self.window.settings
            step = s.get("big_nudge") if ev.modifiers() & Qt.ShiftModifier else s.get("nudge")
            dx, dy = arrows[key][0] * step, arrows[key][1] * step
            tab.push(C.transform_items(tab.doc, ops.top_level_only(scene.selection),
                                       Transform.translation(dx, dy), "Nudge"))
            return True
        return False

    # -- overlay ------------------------------------------------------
    def paint(self, view, painter):
        scene = view.tab.scene
        if scene.selection:
            r = scene.selection_rect()
            live = self.transform if self.dragging and self.mode in ("move", "scale", "rotate") else None
            if live is None:
                view.draw_selection_outlines(painter, scene.selection)
            if r is not None:
                m = qtransform(live) if live else None
                corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
                poly = QPolygonF([view.to_view(m.map(c) if m else c) for c in corners])
                painter.setPen(QPen(ACCENT, 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawPolygon(poly)
                if live is None:
                    pts = self.handle_points(view)
                    painter.drawLine(pts["n"], pts["rotate"])
                    painter.setBrush(QColor("white"))
                    for k, p in pts.items():
                        if k == "rotate":
                            painter.drawEllipse(p, HANDLE / 2, HANDLE / 2)
                        else:
                            painter.drawRect(self.handle_rect(p))
        if self.mode == "marquee" and self.dragging:
            rect = QRectF(view.to_view(self.press), view.to_view(self.cur)).normalized()
            painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.DashLine))
            painter.setBrush(QColor(47, 128, 237, 30))
            painter.drawRect(rect)
