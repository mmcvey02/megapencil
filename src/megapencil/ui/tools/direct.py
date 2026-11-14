"""Direct Selection, Add Anchor, Delete Anchor and Convert Anchor tools."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen

from ...model.geometry import constrain_angle
from ...model.path import Anchor, PathData
from .pathedit import HIT, AnchorTool, commit_path, convert_anchor, editable

DRAG_START = 3.0


class DirectSelectTool(AnchorTool):
    name, label, shortcut, icon = "direct", "Direct Selection", "A", "direct"

    def __init__(self, window):
        super().__init__(window)
        self.sel: set = set()  # (item, subpath index, anchor index)
        self._reset()

    def _reset(self) -> None:
        self.mode: str | None = None  # anchors | handle | marquee
        self.press: QPointF | None = None
        self.cur: QPointF | None = None
        self.dragging = False
        self.handle = None  # (item, si, ai, "hin" | "hout")
        self.clicked = None  # anchor pressed without Shift
        self.base: dict = {}  # item -> original local path
        self.live: dict = {}  # item -> edited local path

    def activate(self, view) -> None:
        self.sel = set()

    def deactivate(self, view) -> None:
        self._abort(view)
        self.sel = set()

    def _abort(self, view) -> None:
        for it in self.live:
            view.tab.scene.preview_path(it, None)
        self._reset()

    def _prune(self, view) -> None:
        items = set(map(id, self.targets(view)))
        self.sel = {(it, si, ai) for it, si, ai in self.sel
                    if id(it) in items and si < len(it.local_path().subpaths)
                    and ai < len(it.local_path().subpaths[si].anchors)}

    def select_all_anchors(self, item) -> None:
        for si, s in enumerate(item.local_path().subpaths):
            for ai in range(len(s.anchors)):
                self.sel.add((item, si, ai))

    def handle_at(self, view, vpos: QPointF):
        vt = view.viewportTransform()
        for it, si, ai in self.sel:
            a = it.local_path().subpaths[si].anchors[ai]
            t = it.world_transform()
            for which in ("hin", "hout"):
                h = getattr(a, which)
                if h is None:
                    continue
                p = vt.map(QPointF(*t.map(*h)))
                if max(abs(p.x() - vpos.x()), abs(p.y() - vpos.y())) <= HIT:
                    return (it, si, ai, which)
        return None

    # -- mouse --------------------------------------------------------
    def mouse_press(self, view, ev, pos):
        self._abort(view)
        self._prune(view)
        self.press = self.cur = pos
        vpos = ev.position()
        mods = ev.modifiers()
        shift, alt = bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier)
        h = self.handle_at(view, vpos)
        if h:
            self.mode, self.handle = "handle", h
            self.base = {h[0]: h[0].local_path()}
            return
        hit = self.anchor_at(view, vpos)
        if hit:
            if alt:
                it, si, ai = hit
                new = commit_path(view.tab, it, convert_anchor(it.local_path(), si, ai), "Convert Anchor")
                self.sel = {(new, si, ai)} if new else set()
                return
            if shift:
                self.sel ^= {hit}
            elif hit not in self.sel:
                self.sel = {hit}
            else:
                self.clicked = hit
            if hit in self.sel:
                self._begin_anchor_drag()
            return
        item = self.pick_item(view, pos, add=shift)
        if item is not None:
            if not shift:
                self.sel = set()
            if editable(item):
                self.select_all_anchors(item)
                self._begin_anchor_drag()
            return
        self.mode = "marquee"

    def _begin_anchor_drag(self) -> None:
        self.mode = "anchors"
        self.base = {it: it.local_path() for it, _, _ in self.sel}

    def mouse_move(self, view, ev, pos):
        if self.press is None or self.mode is None:
            return
        self.cur = pos
        if not self.dragging:
            if (view.to_view(pos) - view.to_view(self.press)).manhattanLength() < DRAG_START:
                return
            self.dragging = True
        mods = ev.modifiers()
        if self.mode == "anchors":
            dx, dy = pos.x() - self.press.x(), pos.y() - self.press.y()
            if mods & Qt.ShiftModifier:
                dx, dy = constrain_angle(dx, dy, 45.0)
            self.live = self._moved(dx, dy)
        elif self.mode == "handle":
            self.live = self._handle_moved(pos, bool(mods & Qt.AltModifier))
        for it, path in self.live.items():
            view.tab.scene.preview_path(it, path)
        view.refresh()

    def _moved(self, dx: float, dy: float) -> dict:
        """Paths with the selected anchors moved by (dx, dy) in document space."""
        out = {}
        for it, base in self.base.items():
            t = it.world_transform()
            inv = t.inverted()

            def shift(p):
                wx, wy = t.map(*p)
                return inv.map(wx + dx, wy + dy)

            new = base.copy()
            for item, si, ai in self.sel:
                if item is it:
                    a = base.subpaths[si].anchors[ai]
                    x, y = shift(a.p)
                    new.subpaths[si].anchors[ai] = Anchor(x, y, shift(a.hin) if a.hin else None,
                                                          shift(a.hout) if a.hout else None, a.smooth)
            out[it] = new
        return out

    def _handle_moved(self, pos: QPointF, break_smooth: bool) -> dict:
        it, si, ai, which = self.handle
        base = self.base[it]
        a = base.subpaths[si].anchors[ai].copy()
        p = it.world_transform().inverted().map(pos.x(), pos.y())
        setattr(a, which, p)
        other = "hout" if which == "hin" else "hin"
        o = getattr(a, other)
        if break_smooth:
            a.smooth = False
        elif a.smooth and o is not None:
            ln = math.hypot(o[0] - a.x, o[1] - a.y)
            d = math.hypot(p[0] - a.x, p[1] - a.y)
            if d > 1e-9:
                setattr(a, other, (a.x - (p[0] - a.x) / d * ln, a.y - (p[1] - a.y) / d * ln))
        return {it: base.with_anchor(si, ai, a)}

    def mouse_release(self, view, ev, pos):
        tab, scene = view.tab, view.tab.scene
        mode, dragging, live = self.mode, self.dragging, self.live
        shift = bool(ev.modifiers() & Qt.ShiftModifier)
        if mode in ("anchors", "handle") and dragging and live:
            self._commit(view, live, "Move Anchors" if mode == "anchors" else "Edit Handle")
        elif mode == "anchors" and not dragging and self.clicked is not None:
            self.sel = {self.clicked}  # a plain click narrows the selection to that anchor
        elif mode == "marquee":
            if dragging:
                rect = QRectF(self.press, pos).normalized()
                items = [i for i in scene.items_in_rect(rect, deep=True) if editable(i)]
                found = set()
                for it in items:
                    t = it.world_transform()
                    for si, s in enumerate(it.local_path().subpaths):
                        for ai, a in enumerate(s.anchors):
                            if rect.contains(QPointF(*t.map(a.x, a.y))):
                                found.add((it, si, ai))
                hit_items = list(dict.fromkeys(it for it, _, _ in found))
                if shift:
                    scene.set_selection(scene.selection + [i for i in hit_items if i not in scene.selection])
                    self.sel |= found
                else:
                    scene.set_selection(hit_items)
                    self.sel = found
            elif not shift:
                scene.set_selection([])
                self.sel = set()
        self._reset()

    def _commit(self, view, paths: dict, text: str) -> None:
        tab = view.tab
        mapping = {}
        if len(paths) > 1:
            tab.stack.beginMacro(text)
        for it, path in paths.items():
            view.tab.scene.preview_path(it, None)
            mapping[it] = commit_path(tab, it, path, text)
        if len(paths) > 1:
            tab.stack.endMacro()
        self.sel = {(mapping.get(it, it), si, ai) for it, si, ai in self.sel if mapping.get(it, it) is not None}
        self._prune(view)

    # -- keys ---------------------------------------------------------
    def delete_pressed(self, view) -> bool:
        self._prune(view)
        if not self.sel:
            return False
        paths = {}
        for it in {it for it, _, _ in self.sel}:
            path = it.local_path()
            for si, ai in sorted(((si, ai) for i, si, ai in self.sel if i is it), reverse=True):
                if si < len(path.subpaths) and ai < len(path.subpaths[si].anchors):
                    whole = len(path.subpaths[si].anchors) <= 2
                    path = path.delete_anchor(si, ai)
                    if whole:
                        break
            paths[it] = path
        self.sel = set()
        self._commit(view, paths, "Delete Anchors")
        return True

    def key_press(self, view, ev) -> bool:
        key = ev.key()
        if key == Qt.Key_Escape:
            self._abort(view)
            self.sel = set()
            return True
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        self._prune(view)
        if key in arrows and self.sel and self.mode is None:
            s = self.window.settings
            step = s.get("big_nudge") if ev.modifiers() & Qt.ShiftModifier else s.get("nudge")
            self.base = {it: it.local_path() for it, _, _ in self.sel}
            paths = self._moved(arrows[key][0] * step, arrows[key][1] * step)
            self.base = {}
            self._commit(view, paths, "Nudge Anchors")
            return True
        return False

    # -- overlay ------------------------------------------------------
    def paint(self, view, painter):
        if not self.dragging:
            self._prune(view)
            self.draw_anchors(view, painter, self.sel)
        if self.mode == "marquee" and self.dragging:
            rect = QRectF(view.to_view(self.press), view.to_view(self.cur)).normalized()
            painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.DashLine))
            painter.setBrush(QColor(47, 128, 237, 30))
            painter.drawRect(rect)


class AddAnchorTool(AnchorTool):
    name, label, shortcut, icon = "add_anchor", "Add Anchor Point", "+", "add_anchor"
    cursor = Qt.CrossCursor

    def mouse_press(self, view, ev, pos):
        hit = self.segment_at(view, pos)
        if hit is None:
            item = self.pick_item(view, pos)
            hit = self.segment_at(view, pos, [item]) if item is not None and editable(item) else None
            if item is None:
                view.tab.scene.set_selection([])
        if hit:
            it, si, seg, t = hit
            commit_path(view.tab, it, it.local_path().insert_anchor(si, seg, t), "Add Anchor Point")

    def paint(self, view, painter):
        self.draw_anchors(view, painter, with_handles=False)


class DeleteAnchorTool(AnchorTool):
    name, label, shortcut, icon = "delete_anchor", "Delete Anchor Point", "-", "delete_anchor"
    cursor = Qt.CrossCursor

    def mouse_press(self, view, ev, pos):
        hit = self.anchor_at(view, ev.position())
        if hit is None:
            item = self.pick_item(view, pos)
            if item is None:
                view.tab.scene.set_selection([])
            return
        it, si, ai = hit
        commit_path(view.tab, it, it.local_path().delete_anchor(si, ai), "Delete Anchor Point")

    def paint(self, view, painter):
        self.draw_anchors(view, painter, with_handles=False)


class ConvertAnchorTool(AnchorTool):
    """Click an anchor to make it a corner; drag from it to pull out smooth handles."""

    name, label, shortcut, icon = "convert", "Convert Anchor Point", "Shift+C", "convert"
    cursor = Qt.CrossCursor

    def __init__(self, window):
        super().__init__(window)
        self.hit = None
        self.base: PathData | None = None
        self.live: PathData | None = None

    def deactivate(self, view) -> None:
        if self.hit and self.live is not None:
            view.tab.scene.preview_path(self.hit[0], None)
        self.hit = self.base = self.live = None

    def mouse_press(self, view, ev, pos):
        self.hit = self.anchor_at(view, ev.position())
        self.live = None
        if self.hit is None:
            if self.pick_item(view, pos) is None:
                view.tab.scene.set_selection([])
            return
        self.base = self.hit[0].local_path()

    def mouse_move(self, view, ev, pos):
        if not self.hit:
            return
        it, si, ai = self.hit
        a = self.base.subpaths[si].anchors[ai]
        p = it.world_transform().inverted().map(pos.x(), pos.y())
        if math.hypot(p[0] - a.x, p[1] - a.y) * view.zoom < 3:
            return
        new = Anchor(a.x, a.y, (2 * a.x - p[0], 2 * a.y - p[1]), p, smooth=True)
        self.live = self.base.with_anchor(si, ai, new)
        view.tab.scene.preview_path(it, self.live)
        view.refresh()

    def mouse_release(self, view, ev, pos):
        if not self.hit:
            return
        it, si, ai = self.hit
        if self.live is not None:
            view.tab.scene.preview_path(it, None)
            path = self.live
        else:
            a = self.base.subpaths[si].anchors[ai]
            path = self.base.with_anchor(si, ai, Anchor(a.x, a.y))
        if path != self.base:
            commit_path(view.tab, it, path, "Convert Anchor Point")
        self.hit = self.base = self.live = None

    def paint(self, view, painter):
        sel = {self.hit} if self.hit else set()
        self.draw_anchors(view, painter, sel)
