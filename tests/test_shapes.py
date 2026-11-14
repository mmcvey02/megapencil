"""Milestone 2: shape tools."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor

from helpers import approx, drag
from megapencil.model.items import EllipseItem, LineItem, RectItem
from megapencil.model.paint import Color


def items(window):
    return list(window.tab.doc.all_items())


def test_draw_rectangle_with_fill_stroke_and_radius(window, qapp):
    view = window.tab.view
    view.actual_size()
    window.state.set(fill=Color(255, 0, 0), stroke=Color(0, 0, 255), stroke_width=4.0, corner_radius=10.0)
    window.set_tool("rect")
    drag(view, (100, 100), (300, 220))
    (r,) = items(window)
    assert isinstance(r, RectItem) and approx((r.x, r.y, r.w, r.h), (100, 100, 200, 120))
    assert r.fill == Color(255, 0, 0) and r.stroke == Color(0, 0, 255) and r.stroke_width == 4 and r.rx == 10
    assert window.selection() == [r]
    qapp.processEvents()
    img = view.viewport().grab().toImage()
    assert img.pixelColor(view.to_view(QPointF(200, 160)).toPoint()) == QColor(255, 0, 0)
    assert img.pixelColor(view.to_view(QPointF(200, 100)).toPoint()) == QColor(0, 0, 255)
    assert img.pixelColor(view.to_view(QPointF(99, 99)).toPoint()) == QColor("white")  # rounded corner
    window.undo()
    assert items(window) == []
    window.redo()
    assert items(window) == [r]


def test_shift_and_alt_constraints(window, qapp):
    view = window.tab.view
    view.actual_size()
    window.set_tool("rect")
    drag(view, (100, 100), (200, 160), Qt.ShiftModifier)
    r = items(window)[-1]
    assert approx((r.w, r.h), (100, 100))
    window.set_tool("ellipse")
    drag(view, (400, 300), (450, 320), Qt.AltModifier)
    e = items(window)[-1]
    assert isinstance(e, EllipseItem) and approx((e.cx, e.cy, e.rx, e.ry), (400, 300, 50, 20))
    drag(view, (500, 100), (560, 130), Qt.ShiftModifier)
    c = items(window)[-1]
    assert approx((c.rx,), (c.ry,), 0.01) and approx((c.rx,), (30,))
    window.set_tool("line")
    drag(view, (100, 400), (200, 410), Qt.ShiftModifier)
    ln = items(window)[-1]
    assert isinstance(ln, LineItem) and abs(ln.y2 - ln.y1) < 1e-6 and ln.fill is None and ln.stroke is not None
    drag(view, (100, 450), (200, 540), Qt.ShiftModifier)
    d = items(window)[-1]
    assert abs(abs(d.x2 - d.x1) - abs(d.y2 - d.y1)) < 1e-6


def test_tiny_drag_and_locked_layer_create_nothing(window, qapp):
    view = window.tab.view
    view.actual_size()
    window.set_tool("rect")
    drag(view, (100, 100), (101, 101))
    assert items(window) == []
    window.tab.doc.layers[0].locked = True
    drag(view, (100, 100), (300, 300))
    assert items(window) == []
