"""Tool base class.  Tools are shared by all documents; every event
receives the view it happened in."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen

ACCENT = QColor("#2f80ed")
HANDLE = 7.0  # handle size in view pixels


class Tool:
    name = "tool"
    label = "Tool"
    shortcut = ""
    icon = ""
    cursor = Qt.ArrowCursor

    def __init__(self, window):
        self.window = window

    # lifecycle
    def activate(self, view) -> None:
        pass

    def deactivate(self, view) -> None:
        pass

    # events: pos is in document coordinates
    def mouse_press(self, view, ev, pos: QPointF) -> None:
        pass

    def mouse_move(self, view, ev, pos: QPointF) -> None:
        pass

    def mouse_release(self, view, ev, pos: QPointF) -> None:
        pass

    def double_click(self, view, ev, pos: QPointF) -> None:
        pass

    def key_press(self, view, ev) -> bool:
        return False

    def undo_step(self, view) -> bool:
        """Give the tool a chance to consume Undo (e.g. pen in progress)."""
        return False

    def delete_pressed(self, view) -> bool:
        """Give the tool a chance to consume Delete (e.g. delete anchors)."""
        return False

    def paint(self, view, painter) -> None:
        """Draw overlays in view (pixel) coordinates."""

    # helpers
    @staticmethod
    def outline_pen() -> QPen:
        return QPen(ACCENT, 1)

    @staticmethod
    def handle_rect(p: QPointF, size: float = HANDLE) -> QRectF:
        return QRectF(p.x() - size / 2, p.y() - size / 2, size, size)

    def target_layer(self, view):
        """Active layer if it can receive new objects, else None (with a message)."""
        layer = view.tab.scene.active_layer
        if layer is None or not layer.editable():
            self.window.status_message("The active layer is locked or hidden.")
            return None
        return layer
