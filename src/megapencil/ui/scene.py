"""QGraphicsScene that mirrors a Document.

Each leaf item has one ``ItemGraphic`` (painted in C++ by QGraphicsPathItem)
holding the item's path already mapped to document coordinates, so strokes
are never distorted by transforms.  Layers are invisible parent items that
carry visibility and opacity.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsScene

from ..model.items import Document, GroupItem, Item, Layer
from ..model.path import PathData
from .qtbridge import make_brush, make_pen, qtransform, to_qpath

PASTEBOARD_MARGIN = 4000.0


class LayerGraphic(QGraphicsItem):
    def __init__(self, layer: Layer):
        super().__init__()
        self.layer = layer
        self.setFlag(QGraphicsItem.ItemHasNoContents, True)

    def boundingRect(self) -> QRectF:
        return QRectF()

    def paint(self, *a) -> None:  # pragma: no cover - never called
        pass

    def sync(self) -> None:
        self.setVisible(self.layer.visible)
        self.setOpacity(self.layer.opacity)


class ItemGraphic(QGraphicsPathItem):
    def __init__(self, item: Item):
        super().__init__()
        self.item = item
        self.sync()

    def sync(self, path: PathData | None = None) -> None:
        it = self.item
        local = path if path is not None else it.local_path()
        world = qtransform(it.world_transform())
        qp = world.map(to_qpath(local))
        qp.setFillRule(Qt.WindingFill)
        b = local.bounds()
        bbox = QRectF(b[0], b[1], b[2] - b[0], b[3] - b[1]) if b else QRectF()
        self.setPath(qp)
        self.setBrush(make_brush(it.fill, bbox, world))
        self.setPen(make_pen(it, bbox, world))
        self.setOpacity(it.effective_opacity())
        vis = True
        p = it
        while isinstance(p, Item):
            vis = vis and p.visible
            p = p.parent
        self.setVisible(vis)

    def hit(self, rect: QRectF) -> bool:
        """Precise hit test: fill area if filled, otherwise the stroke."""
        path = self.path()
        if self.item.fill is not None and path.intersects(rect):
            return True
        if self.item.fill is not None and path.contains(rect.center()):
            return True
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.item.stroke_width if self.item.stroke is not None else 0.0, rect.width()))
        return stroker.createStroke(path).intersects(rect)


class DocumentScene(QGraphicsScene):
    selectionChangedSignal = Signal()
    documentChanged = Signal(str)

    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.graphics: dict[int, ItemGraphic] = {}
        self.layer_graphics: dict[int, LayerGraphic] = {}
        self.selection: list[Item] = []
        self.active_layer: Layer | None = doc.layers[-1] if doc.layers else None
        self.pasteboard_color = QColor(83, 83, 83)
        self.setItemIndexMethod(QGraphicsScene.BspTreeIndex)
        doc.listeners.append(self._on_doc_change)
        self._update_rect()
        self.rebuild()

    # -- sync ---------------------------------------------------------
    def _update_rect(self) -> None:
        m = PASTEBOARD_MARGIN
        self.setSceneRect(-m, -m, self.doc.width + 2 * m, self.doc.height + 2 * m)

    def _on_doc_change(self, kind: str, objs: list) -> None:
        if kind == "structure":
            self.rebuild()
            self._prune_selection()
        elif kind == "props":
            for o in objs:
                if isinstance(o, Layer):
                    g = self.layer_graphics.get(id(o))
                    if g:
                        g.sync()
                elif isinstance(o, Item):
                    for leaf in o.leaves():
                        g = self.graphics.get(id(leaf))
                        if g:
                            g.sync()
        elif kind == "doc":
            self._update_rect()
            self.update()
        self.documentChanged.emit(kind)

    def rebuild(self) -> None:
        """Synchronise the graphics tree with the document structure."""
        live_layers, live_items = set(), set()
        for li, layer in enumerate(self.doc.children):
            lg = self.layer_graphics.get(id(layer))
            if lg is None:
                lg = LayerGraphic(layer)
                self.layer_graphics[id(layer)] = lg
                self.addItem(lg)
            lg.setZValue(li)
            lg.sync()
            live_layers.add(id(layer))
            z = 0
            for top in layer.children:
                for leaf in top.leaves():
                    if isinstance(leaf, GroupItem):
                        continue
                    g = self.graphics.get(id(leaf))
                    if g is None:
                        g = ItemGraphic(leaf)
                        self.graphics[id(leaf)] = g
                    else:
                        g.sync()
                    if g.parentItem() is not lg:
                        g.setParentItem(lg)
                    g.setZValue(z)
                    z += 1
                    live_items.add(id(leaf))
        for key in [k for k in self.graphics if k not in live_items]:
            g = self.graphics.pop(key)
            g.setParentItem(None)
            if g.scene() is self:
                self.removeItem(g)
        for key in [k for k in self.layer_graphics if k not in live_layers]:
            self.removeItem(self.layer_graphics.pop(key))
        if self.active_layer not in self.doc.children:
            self.active_layer = self.doc.children[-1] if self.doc.children else None

    # -- selection ----------------------------------------------------
    def set_selection(self, items) -> None:
        items = list(dict.fromkeys(items))
        if items != self.selection:
            self.selection = items
            self.selectionChangedSignal.emit()
            self.update()

    def _prune_selection(self) -> None:
        keep = [it for it in self.selection if self.doc.contains(it)]
        if keep != self.selection:
            self.set_selection(keep)

    def selectable_items(self) -> list[Item]:
        out = []
        for layer in self.doc.children:
            if layer.editable():
                out += [it for it in layer.children if it.visible and not it.locked]
        return out

    # -- hit testing --------------------------------------------------
    def _resolve(self, g, deep: bool) -> Item | None:
        if not isinstance(g, ItemGraphic):
            return None
        it = g.item
        layer = it.layer()
        if layer is None or not layer.editable() or it.effectively_locked():
            return None
        return it if deep else it.top_level()

    def item_at(self, pos, tol: float, deep: bool = False) -> Item | None:
        rect = QRectF(pos.x() - tol, pos.y() - tol, 2 * tol, 2 * tol)
        for g in self.items(rect, Qt.IntersectsItemBoundingRect, Qt.DescendingOrder):
            it = self._resolve(g, deep)
            if it is not None and g.hit(rect):
                return it
        return None

    def items_in_rect(self, rect: QRectF, deep: bool = False) -> list[Item]:
        out = []
        for g in self.items(rect, Qt.IntersectsItemShape, Qt.AscendingOrder):
            it = self._resolve(g, deep)
            if it is not None:
                out.append(it)
        return list(dict.fromkeys(out))

    # -- previews (cheap, during drags) -------------------------------
    def preview_transform(self, items, t: QTransform | None) -> None:
        for it in items:
            for leaf in it.leaves():
                g = self.graphics.get(id(leaf))
                if g:
                    g.setTransform(t if t is not None else QTransform())

    def preview_path(self, item: Item, path: PathData | None) -> None:
        g = self.graphics.get(id(item))
        if g:
            g.sync(path)

    def outline_of(self, item: Item) -> QPainterPath:
        qp = QPainterPath()
        for leaf in item.leaves():
            g = self.graphics.get(id(leaf))
            if g:
                qp.addPath(g.path())
        return qp

    # -- background ---------------------------------------------------
    def drawBackground(self, painter, rect) -> None:
        painter.fillRect(rect, self.pasteboard_color)
        page = QRectF(0, 0, self.doc.width, self.doc.height)
        painter.fillRect(page.translated(3, 3), QColor(0, 0, 0, 60))
        painter.fillRect(page, QBrush(Qt.white))
        pen = QPen(QColor(0, 0, 0, 160), 0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(page)
