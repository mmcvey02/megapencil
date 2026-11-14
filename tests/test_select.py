"""Milestone 3: selection tool."""
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from helpers import approx, click, drag
from megapencil.model.items import RectItem
from megapencil.model.paint import Color


@pytest.fixture
def scene3(window, qapp):
    """Three filled rectangles: a (50..150), b (200..300), c (400..500) at y 50..150."""
    tab = window.tab
    tab.view.actual_size()
    out = [tab.doc.add(RectItem(x=x, y=50, w=100, h=100, fill=Color(200, 0, 0))) for x in (50, 200, 400)]
    tab.scene.rebuild()
    window.set_tool("select")
    return window, tab, tab.view, out


def test_click_shift_click_and_deselect(scene3):
    window, tab, view, (a, b, c) = scene3
    click(view, (100, 100))
    assert window.selection() == [a]
    click(view, (250, 100), Qt.ShiftModifier)
    assert window.selection() == [a, b]
    click(view, (100, 100), Qt.ShiftModifier)
    assert window.selection() == [b]
    click(view, (700, 500))
    assert window.selection() == []


def test_unfilled_shape_selects_by_stroke_only(scene3):
    window, tab, view, (a, b, c) = scene3
    tab.push(__import__("megapencil").commands.PropertyCommand(tab.doc, [(a, "fill", None), (a, "stroke", Color(0, 0, 0))]))
    click(view, (100, 100))
    assert window.selection() == []
    click(view, (50, 100))
    assert window.selection() == [a]


def test_marquee_and_shift_marquee(scene3):
    window, tab, view, (a, b, c) = scene3
    drag(view, (20, 20), (320, 200))
    assert window.selection() == [a, b]
    drag(view, (380, 20), (520, 200), Qt.ShiftModifier)
    assert window.selection() == [a, b, c]


def test_move_with_undo_and_shift_constraint(scene3):
    window, tab, view, (a, b, c) = scene3
    drag(view, (100, 100), (160, 130))
    assert approx(a.bounds(), (110, 80, 210, 180))
    window.undo()
    assert approx(a.bounds(), (50, 50, 150, 150), 1e-6)
    drag(view, (100, 100), (160, 110), Qt.ShiftModifier)
    assert approx(a.bounds(), (110, 50, 210, 150), 1.5) and abs(a.bounds()[1] - 50) < 1e-6


def test_scale_handles(scene3):
    window, tab, view, (a, b, c) = scene3
    click(view, (100, 100))
    drag(view, (150, 150), (250, 200))  # south-east handle
    assert approx(a.bounds(), (50, 50, 250, 200))
    drag(view, (250, 125), (150, 125))  # east handle, back to 100 wide
    assert approx(a.bounds(), (50, 50, 150, 200))
    drag(view, (150, 200), (250, 210), Qt.ShiftModifier)  # proportional
    x0, y0, x1, y1 = a.bounds()
    assert abs((x1 - x0) / (y1 - y0) - 100 / 150) < 0.01 and approx((x0, y0), (50, 50))
    assert a.stroke_width == 1.0


def test_rotate_handle(scene3):
    window, tab, view, (a, b, c) = scene3
    click(view, (250, 100))
    handle = view.to_view(QPointF(250, 50)) - QPointF(0, 22)
    start = view.to_scene(handle)
    drag(view, (start.x(), start.y()), (250 + (100 - start.y()), 100), Qt.ShiftModifier)  # quarter turn
    t = b.transform
    assert approx((t.a, t.b, t.c, t.d), (0, 1, -1, 0), 1e-6)
    assert approx(b.bounds(), (200, 50, 300, 150), 1e-6)


def test_nudge_and_delete(scene3, qapp):
    window, tab, view, (a, b, c) = scene3
    click(view, (100, 100))
    view.setFocus()
    QTest.keyClick(view, Qt.Key_Right)
    QTest.keyClick(view, Qt.Key_Down, Qt.ShiftModifier)
    assert approx(a.bounds(), (51, 60, 151, 160), 1e-6)
    window.delete_selection()
    assert list(tab.doc.all_items()) == [b, c] and window.selection() == []
    window.undo()
    assert list(tab.doc.all_items()) == [a, b, c]


def test_alt_drag_duplicates(scene3):
    window, tab, view, (a, b, c) = scene3
    drag(view, (100, 100), (100, 300), Qt.AltModifier)
    items = list(tab.doc.all_items())
    assert len(items) == 4 and approx(a.bounds(), (50, 50, 150, 150), 1e-6)
    assert approx(window.selection()[0].bounds(), (50, 250, 150, 350))


def test_locked_and_hidden_are_not_selectable(scene3):
    window, tab, view, (a, b, c) = scene3
    click(view, (100, 100))
    window.set_flag("locked", True)
    click(view, (100, 100))
    assert window.selection() == []
    window.select_all()
    assert window.selection() == [b, c]
    window.set_flag_all("locked", False)
    window.select_all()
    assert window.selection() == [a, b, c]


def test_control_bar_geometry(scene3, qapp):
    window, tab, view, (a, b, c) = scene3
    click(view, (100, 100))
    qapp.processEvents()
    geo = window.controlbar.geo
    assert [geo[k].value() for k in "XYWH"] == [50, 50, 100, 100]
    geo["W"].setValue(200)
    geo["X"].setValue(10)
    assert approx(a.bounds(), (10, 50, 210, 150), 1e-6)
    window.controlbar.opacity.setValue(50)
    assert a.opacity == 0.5
