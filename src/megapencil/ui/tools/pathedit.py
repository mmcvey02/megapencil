"""Shared helpers for tools that edit anchors."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from ... import commands as C
from ...model.items import GroupItem, Item, PathItem, TextItem
from ...model.path import Anchor, PathData
from .base import ACCENT, Tool

HIT = 5.0  # view pixels
MAX_DRAWN_ANCHORS = 4000


def editable(item) -> bool:
    return isinstance(item, Item) and not isinstance(item, (TextItem, GroupItem))


def commit_path(tab, item: Item, path: PathData, text: str) -> Item | None:
    """Store a new local path on ``item`` (shapes become paths). Returns the
    item now holding the path, or None if the item was deleted."""
    doc, scene = tab.doc, tab.scene
    if path.is_empty():
        scene.set_selection([i for i in scene.selection if i is not item])
        tab.push(C.delete_items(doc, [item], text))
        return None
    if isinstance(item, PathItem):
        tab.push(C.PropertyCommand(doc, [(item, "path", path)], text))
        return item
    new = item.to_path_item()
    new.path = path
    sel = [new if i is item else i for i in scene.selection]
    tab.push(C.replace_item(doc, item, new, text))
    scene.set_selection(sel)
    return new


def convert_anchor(path: PathData, si: int, ai: int) -> PathData:
    """Toggle an anchor between corner and smooth."""
    new = path.copy()
    s = new.subpaths[si]
    a = s.anchors[ai]
    if a.hin is not None or a.hout is not None:
        s.anchors[ai] = Anchor(a.x, a.y)
        return new
    n = len(s.anchors)
    prev = s.anchors[(ai - 1) % n] if (ai > 0 or s.closed) else None
    nxt = s.anchors[(ai + 1) % n] if (ai < n - 1 or s.closed) else None
    if prev is None and nxt is None:
        return new
    p0 = prev.p if prev else a.p
    p1 = nxt.p if nxt else a.p
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    if ln < 1e-9:
        return new
    dx, dy = dx / ln, dy / ln
    hin = hout = None
    if prev:
        k = math.hypot(a.x - prev.x, a.y - prev.y) / 3
        hin = (a.x - dx * k, a.y - dy * k)
    if nxt:
        k = math.hypot(nxt.x - a.x, nxt.y - a.y) / 3
        hout = (a.x + dx * k, a.y + dy * k)
    s.anchors[ai] = Anchor(a.x, a.y, hin, hout, smooth=bool(hin and hout))
    return new


class AnchorTool(Tool):
    """Base for tools working on anchors of the selected (leaf) items."""

    cursor = Qt.ArrowCursor

    def targets(self, view) -> list[Item]:
        return [leaf for it in view.tab.scene.selection for leaf in it.leaves() if editable(leaf)]

    def anchor_at(self, view, vpos: QPointF, items=None):
        """Return (item, subpath index, anchor index) under the view position."""
        best, best_d = None, HIT
        for it in (items if items is not None else self.targets(view)):
            t = it.world_transform()
            vt = view.viewportTransform()
            for si, s in enumerate(it.local_path().subpaths):
                for ai, a in enumerate(s.anchors):
                    p = vt.map(QPointF(*t.map(a.x, a.y)))
                    d = max(abs(p.x() - vpos.x()), abs(p.y() - vpos.y()))
                    if d <= best_d:
                        best, best_d = (it, si, ai), d
        return best

    def segment_at(self, view, pos: QPointF, items=None):
        """Return (item, subpath index, segment index, t) near a document position."""
        best, best_d = None, view.px(HIT)
        for it in (items if items is not None else self.targets(view)):
            hit = it.world_path().nearest_segment(pos.x(), pos.y())
            if hit and hit[3] <= best_d:
                best, best_d = (it, hit[0], hit[1], hit[2]), hit[3]
        return best

    def pick_item(self, view, pos: QPointF, add: bool = False):
        """Select the leaf item under the cursor; returns it (or None)."""
        scene = view.tab.scene
        item = scene.item_at(pos, view.px(3), deep=True)
        if item is None:
            return None
        if add:
            if item not in scene.selection:
                scene.set_selection(scene.selection + [item])
        elif item not in self.targets(view):
            scene.set_selection([item])
        return item

    def draw_anchors(self, view, painter, selected=frozenset(), with_handles: bool = True) -> None:
        items = self.targets(view)
        view.draw_selection_outlines(painter, view.tab.scene.selection)
        if sum(i.local_path().anchor_count() for i in items[:500]) > MAX_DRAWN_ANCHORS or len(items) > 500:
            return
        vt = view.viewportTransform()
        for it in items:
            t = it.world_transform()
            for si, s in enumerate(it.local_path().subpaths):
                for ai, a in enumerate(s.anchors):
                    p = vt.map(QPointF(*t.map(a.x, a.y)))
                    sel = (it, si, ai) in selected
                    if sel and with_handles:
                        painter.setPen(QPen(ACCENT, 1))
                        for h in (a.hin, a.hout):
                            if h is not None:
                                hp = vt.map(QPointF(*t.map(*h)))
                                painter.drawLine(p, hp)
                                painter.setBrush(ACCENT)
                                painter.drawEllipse(hp, 3, 3)
                    painter.setPen(QPen(ACCENT, 1))
                    painter.setBrush(ACCENT if sel else QColor("white"))
                    painter.drawRect(self.handle_rect(p, 6))
