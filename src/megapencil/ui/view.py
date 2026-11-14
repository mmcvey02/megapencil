"""Canvas view: zoom, pan, tool dispatch, overlays, guides."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QTransform
from PySide6.QtWidgets import QGraphicsView

from ..commands import PropertyCommand

MIN_ZOOM, MAX_ZOOM = 0.02, 64.0
GUIDE_COLOR = QColor(0, 190, 230)


class CanvasView(QGraphicsView):
    zoomChanged = Signal(float)
    cursorMoved = Signal(QPointF)

    def __init__(self, tab):
        super().__init__(tab.scene)
        self.tab = tab
        self.tool = None
        self.zoom = 1.0
        self.guides_visible = True
        self.guides_locked = False
        self.guide_drag: tuple[str, float | None, int | None] | None = None  # orient, pos, index
        self._space = False
        self._panning = None
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setDragMode(QGraphicsView.NoDrag)

    # -- coordinates --------------------------------------------------
    def to_view(self, p: QPointF) -> QPointF:
        return self.viewportTransform().map(p)

    def to_scene(self, p: QPointF) -> QPointF:
        return self.viewportTransform().inverted()[0].map(QPointF(p))

    def px(self, n: float) -> float:
        """Length of ``n`` view pixels in document units."""
        return n / self.zoom

    def refresh(self) -> None:
        self.viewport().update()

    # -- zoom / pan ---------------------------------------------------
    def set_zoom(self, z: float, anchor: QPointF | None = None) -> None:
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if anchor is None:
            anchor = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
        before = self.to_scene(anchor)
        self.zoom = z
        self.setTransform(QTransform.fromScale(z, z))
        after = self.to_scene(anchor)
        d = (after - before) * z
        self.pan_by(d.x(), d.y())
        self.zoomChanged.emit(z)
        self.refresh()

    def pan_by(self, dx: float, dy: float) -> None:
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(int(round(h.value() - dx)))
        v.setValue(int(round(v.value() - dy)))

    def zoom_to_rect(self, rect: QRectF, margin: float = 0.0) -> None:
        vw, vh = max(self.viewport().width() - 2 * margin, 10), max(self.viewport().height() - 2 * margin, 10)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self.set_zoom(min(vw / rect.width(), vh / rect.height()))
        self.centerOn(rect.center())
        self.zoomChanged.emit(self.zoom)

    def fit_artboard(self) -> None:
        doc = self.tab.doc
        self.zoom_to_rect(QRectF(0, 0, doc.width, doc.height), margin=40)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.25)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    # -- tools --------------------------------------------------------
    def set_tool(self, tool) -> None:
        if self.tool is tool:
            return
        if self.tool is not None:
            self.tool.deactivate(self)
        self.tool = tool
        if tool is not None:
            tool.activate(self)
            self.viewport().setCursor(tool.cursor)
        self.refresh()

    # -- events -------------------------------------------------------
    def wheelEvent(self, ev) -> None:
        if ev.modifiers() & Qt.ControlModifier:
            steps = ev.angleDelta().y() / 120.0
            self.set_zoom(self.zoom * (1.15 ** steps), ev.position())
            ev.accept()
        else:
            super().wheelEvent(ev)

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat() and not self.tab.is_text_editing():
            self._space = True
            self.viewport().setCursor(Qt.OpenHandCursor)
            return
        if ev.key() == Qt.Key_Space:
            return
        if self.tool is not None and self.tool.key_press(self, ev):
            self.refresh()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat():
            self._space = False
            if self._panning is None and self.tool is not None:
                self.viewport().setCursor(self.tool.cursor)
            return
        super().keyReleaseEvent(ev)

    def mousePressEvent(self, ev) -> None:
        self.setFocus()
        if ev.button() == Qt.MiddleButton or (ev.button() == Qt.LeftButton and self._space):
            self._panning = ev.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if ev.button() == Qt.LeftButton and self.tool is not None:
            self.tool.mouse_press(self, ev, self.to_scene(ev.position()))
            self.refresh()

    def mouseMoveEvent(self, ev) -> None:
        pos = self.to_scene(ev.position())
        self.cursorMoved.emit(pos)
        if self._panning is not None:
            d = ev.position() - self._panning
            self._panning = ev.position()
            self.pan_by(d.x(), d.y())
            return
        if self.tool is not None:
            self.tool.mouse_move(self, ev, pos)

    def mouseReleaseEvent(self, ev) -> None:
        if self._panning is not None:
            self._panning = None
            cur = Qt.OpenHandCursor if self._space else (self.tool.cursor if self.tool else Qt.ArrowCursor)
            self.viewport().setCursor(cur)
            return
        if ev.button() == Qt.LeftButton and self.tool is not None:
            self.tool.mouse_release(self, ev, self.to_scene(ev.position()))
            self.refresh()

    def mouseDoubleClickEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self.tool is not None:
            self.tool.mouse_press(self, ev, self.to_scene(ev.position()))
            self.tool.double_click(self, ev, self.to_scene(ev.position()))
            self.refresh()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.zoomChanged.emit(self.zoom)  # rulers follow scrolling

    # -- guides -------------------------------------------------------
    def guide_at(self, view_pos: QPointF, tol: float = 4.0) -> int | None:
        if not self.guides_visible or self.guides_locked:
            return None
        for i, (o, p) in enumerate(self.tab.doc.guides):
            v = self.to_view(QPointF(p, p))
            d = abs(view_pos.y() - v.y()) if o == "h" else abs(view_pos.x() - v.x())
            if d <= tol:
                return i
        return None

    def begin_guide_drag(self, orient: str, index: int | None = None) -> None:
        self.guide_drag = (orient, None, index)

    def update_guide_drag(self, view_pos: QPointF) -> None:
        if self.guide_drag is None:
            return
        o, _, idx = self.guide_drag
        inside = self.viewport().rect().contains(view_pos.toPoint())
        sp = self.to_scene(view_pos)
        self.guide_drag = (o, (sp.y() if o == "h" else sp.x()) if inside else None, idx)
        self.cursorMoved.emit(sp)
        self.refresh()

    def finish_guide_drag(self) -> None:
        if self.guide_drag is None:
            return
        o, pos, idx = self.guide_drag
        self.guide_drag = None
        doc = self.tab.doc
        guides = list(doc.guides)
        if idx is not None:
            if pos is None:
                del guides[idx]
                text = "Delete Guide"
            else:
                guides[idx] = (o, round(pos, 2))
                text = "Move Guide"
        elif pos is not None:
            guides.append((o, round(pos, 2)))
            text = "Add Guide"
        else:
            self.refresh()
            return
        self.tab.push(PropertyCommand(doc, [(doc, "guides", tuple(guides))], text))
        self.refresh()

    # -- overlays -----------------------------------------------------
    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.viewport().width(), self.viewport().height()
        if self.guides_visible:
            painter.setPen(QPen(GUIDE_COLOR, 1))
            skip = self.guide_drag[2] if self.guide_drag else None
            for i, (o, p) in enumerate(self.tab.doc.guides):
                if i != skip:
                    self._draw_guide(painter, o, p, w, h)
            if self.guide_drag and self.guide_drag[1] is not None:
                painter.setPen(QPen(GUIDE_COLOR, 1, Qt.DashLine))
                self._draw_guide(painter, self.guide_drag[0], self.guide_drag[1], w, h)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.tool is not None:
            self.tool.paint(self, painter)
        painter.restore()

    def _draw_guide(self, painter, o: str, p: float, w: int, h: int) -> None:
        v = self.to_view(QPointF(p, p))
        if o == "h":
            y = round(v.y()) + 0.5
            painter.drawLine(QPointF(0, y), QPointF(w, y))
        else:
            x = round(v.x()) + 0.5
            painter.drawLine(QPointF(x, 0), QPointF(x, h))

    def draw_selection_outlines(self, painter, items, limit: int = 300) -> None:
        """Thin outlines of selected items (skipped for very large selections)."""
        if len(items) > limit:
            return
        vt = self.viewportTransform()
        painter.setPen(QPen(QColor("#2f80ed"), 1))
        painter.setBrush(Qt.NoBrush)
        for it in items:
            painter.drawPath(vt.map(self.tab.scene.outline_of(it)))
