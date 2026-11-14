"""Original, programmatically drawn icons (24x24 grid, SVG path snippets)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from ..model.path import PathData
from . import theme
from .qtbridge import to_qpath

_SMALL_PEN = "M9 2 L13 10 L11 15 L7 15 L5 10 Z M9 2 L9 9"
_ARROW = "M6 3 L6 19 L10 15 L13 21 L15 20 L12 14 L18 14 Z"
# name -> list of (path, "f" fill | "s" stroke)
GLYPHS = {
    "select": [(_ARROW, "f")],
    "direct": [(_ARROW, "s")],
    "pen": [("M12 3 L17 13 L14 19 L10 19 L7 13 Z M12 3 L12 12 M9 21.5 L15 21.5", "s"),
            ("M13.4 13 A1.4 1.4 0 1 1 10.6 13 A1.4 1.4 0 1 1 13.4 13 Z", "f")],
    "add_anchor": [(_SMALL_PEN + " M15 18 H22 M18.5 14.5 V21.5", "s")],
    "delete_anchor": [(_SMALL_PEN + " M15 18 H22", "s")],
    "convert": [("M5 19 L12 5 L19 19", "s"), ("M10.5 3.5 H13.5 V6.5 H10.5 Z", "f")],
    "rect": [("M4 6 H20 V18 H4 Z", "s")],
    "ellipse": [("M21 12 A9 7 0 1 1 3 12 A9 7 0 1 1 21 12 Z", "s")],
    "line": [("M5 19 L19 5", "s")],
    "text": [("M5 8 V5 H19 V8 M12 5 V20 M9 20 H15", "s")],
    "hand": [("M8 12 V6 a1.5 1.5 0 0 1 3 0 V11 V4.5 a1.5 1.5 0 0 1 3 0 V11 V5.5 a1.5 1.5 0 0 1 3 0 V12 V8 "
              "a1.5 1.5 0 0 1 3 0 V15 c0 4 -3 6 -6 6 h-1 c-3 0 -4.5 -2 -6 -5 l-1.8 -3.4 a1.4 1.4 0 0 1 2.5 -1.3 Z", "s")],
    "zoom": [("M16 10 A6 6 0 1 1 4 10 A6 6 0 1 1 16 10 Z M14.5 14.5 L20.5 20.5", "s")],
    "eye": [("M2 12 C6 5 18 5 22 12 C18 19 6 19 2 12 Z", "s"), ("M15 12 A3 3 0 1 1 9 12 A3 3 0 1 1 15 12 Z", "f")],
    "lock": [("M6 11 H18 V20 H6 Z", "f"), ("M8.5 11 V8 a3.5 3.5 0 0 1 7 0 V11", "s")],
    "plus": [("M12 5 V19 M5 12 H19", "s")],
    "minus": [("M5 12 H19", "s")],
    "up": [("M12 5 L12 19 M6 11 L12 5 L18 11", "s")],
    "down": [("M12 5 L12 19 M6 13 L12 19 L18 13", "s")],
    "swap": [("M5 9 H17 M13 5 L17 9 L13 13 M19 16 H7 M11 12 L7 16 L11 20", "s")],
    "align_left": [("M4 3 V21", "s"), ("M6 6 H19 V10 H6 Z M6 14 H13 V18 H6 Z", "f")],
    "align_hcenter": [("M12 3 V21", "s"), ("M5 6 H19 V10 H5 Z M8 14 H16 V18 H8 Z", "f")],
    "align_right": [("M20 3 V21", "s"), ("M5 6 H18 V10 H5 Z M11 14 H18 V18 H11 Z", "f")],
    "align_top": [("M3 4 H21", "s"), ("M6 6 H10 V19 H6 Z M14 6 H18 V13 H14 Z", "f")],
    "align_vcenter": [("M3 12 H21", "s"), ("M6 5 H10 V19 H6 Z M14 8 H18 V16 H14 Z", "f")],
    "align_bottom": [("M3 20 H21", "s"), ("M6 5 H10 V18 H6 Z M14 11 H18 V18 H14 Z", "f")],
    "dist_hcenters": [("M4 3 V21 M12 3 V21 M20 3 V21", "s"), ("M2 8 H6 V16 H2 Z M10 6 H14 V18 H10 Z M18 9 H22 V15 H18 Z", "f")],
    "dist_vcenters": [("M3 4 H21 M3 12 H21 M3 20 H21", "s"), ("M8 2 H16 V6 H8 Z M6 10 H18 V14 H6 Z M9 18 H15 V22 H9 Z", "f")],
    "dist_hspace": [("M3 3 V21 M21 3 V21", "s"), ("M6 7 H10 V17 H6 Z M14 7 H18 V17 H14 Z", "f")],
    "dist_vspace": [("M3 3 H21 M3 21 H21", "s"), ("M7 6 H17 V10 H7 Z M7 14 H17 V18 H7 Z", "f")],
}
_cache: dict = {}


def icon(name: str, size: int = 24) -> QIcon:
    color = theme.current()["icon"]
    key = (name, size, color)
    if key in _cache:
        return _cache[key]
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size * dpr / 24, size * dpr / 24)
    col = QColor(color)
    for d, mode in GLYPHS.get(name, []):
        qp = to_qpath(PathData.from_svg(d))
        if mode == "f":
            p.fillPath(qp, col)
        else:
            pen = QPen(col, 1.6)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(qp, pen)
    p.end()
    pm.setDevicePixelRatio(dpr)
    ic = QIcon(pm)
    _cache[key] = ic
    return ic


def swatch_pixmap(paint_brush, size: int = 20, none: bool = False) -> QPixmap:
    """Small square preview of a paint (red slash for 'none')."""
    pm = QPixmap(size, size)
    pm.fill(QColor("#ffffff"))
    p = QPainter(pm)
    if none:
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#e02020"), 2))
        p.drawLine(1, size - 1, size - 1, 1)
    else:
        p.fillRect(QRectF(0, 0, size, size), paint_brush)
    p.setPen(QPen(QColor("#808080"), 1))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return pm
