"""Milestone 4: pen, direct selection, add/delete/convert anchor."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from helpers import approx, click, drag
from megapencil.model.items import PathItem, RectItem
from megapencil.model.paint import Color


@pytest.fixture
def env(window, qapp):
    tab = window.tab
    tab.view.actual_size()
    return window, tab, tab.view


def items(tab):
    return list(tab.doc.all_items())


def anchors(item):
    return item.local_path().subpaths[0].anchors


def test_pen_corner_points_and_enter(env):
    window, tab, view = env
    window.set_tool("pen")
    for p in ((100, 100), (200, 100), (200, 200)):
        click(view, p)
    assert items(tab) == []  # nothing committed yet
    view.setFocus()
    QTest.keyClick(view, Qt.Key_Return)
    (p,) = items(tab)
    assert isinstance(p, PathItem) and not p.path.subpaths[0].closed
    assert [approx(a.p, e) for a, e in zip(anchors(p), ((100, 100), (200, 100), (200, 200)))] == [True] * 3
    assert all(a.hin is None and a.hout is None for a in anchors(p))
    window.undo()
    assert items(tab) == []


def test_pen_drag_makes_smooth_point_and_close(env):
    window, tab, view = env
    window.set_tool("pen")
    click(view, (100, 200))
    drag(view, (200, 100), (250, 100))
    click(view, (300, 200))
    click(view, (100, 200))  # close on first anchor
    (p,) = items(tab)
    s = p.path.subpaths[0]
    assert s.closed and len(s.anchors) == 3
    mid = s.anchors[1]
    assert mid.smooth and approx(mid.hout, (250, 100)) and approx(mid.hin, (150, 100))
    assert p.bounds()[1] < 150  # curve bulges above the chord
    assert window.selection() == [p] and not window.tools["pen"].in_progress()


def test_pen_undo_removes_last_point_and_shift_constrains(env):
    window, tab, view = env
    window.set_tool("pen")
    click(view, (100, 100))
    click(view, (200, 110), Qt.ShiftModifier)
    click(view, (300, 300))
    window.undo()  # consumed by the pen: removes the third point
    assert len(window.tools["pen"].anchors) == 2
    window.set_tool("select")  # switching tools commits
    (p,) = items(tab)
    assert len(anchors(p)) == 2 and abs(anchors(p)[1].y - 100) < 1e-6


def test_pen_continues_open_path(env):
    window, tab, view = env
    window.set_tool("pen")
    click(view, (100, 100))
    click(view, (200, 100))
    window.set_tool("select")
    (p,) = items(tab)
    window.set_tool("pen")
    click(view, (200, 100))  # end point of the selected path
    click(view, (200, 200))
    window.set_tool("select")
    assert items(tab) == [p] and len(anchors(p)) == 3 and approx(anchors(p)[2].p, (200, 200))
    window.set_tool("pen")
    click(view, (100, 100))  # start point: path is extended from the other end
    click(view, (50, 50))
    window.set_tool("select")
    assert len(anchors(p)) == 4 and approx(anchors(p)[-1].p, (50, 50)) and approx(anchors(p)[0].p, (200, 200))


def make_path(tab, window):
    p = tab.doc.add(PathItem(path=__import__("megapencil.model.path", fromlist=["x"]).PathData.from_polygon(
        [(100, 100), (300, 100), (300, 300), (100, 300)]), fill=Color(0, 150, 0)))
    tab.scene.rebuild()
    return p


def test_direct_selection_moves_one_anchor(env):
    window, tab, view = env
    p = make_path(tab, window)
    window.set_tool("direct")
    click(view, (200, 200))  # select the object (all anchors)
    click(view, (300, 100))  # then one anchor
    drag(view, (300, 100), (350, 60))
    assert approx(anchors(p)[1].p, (350, 60)) and approx(anchors(p)[0].p, (100, 100))
    window.undo()
    assert approx(anchors(p)[1].p, (300, 100), 1e-6)
    drag(view, (200, 200), (220, 230))  # dragging the fill moves every anchor
    assert approx(p.bounds(), (120, 130, 320, 330))


def test_direct_selection_marquee_delete_and_handles(env):
    window, tab, view = env
    p = make_path(tab, window)
    window.set_tool("direct")
    drag(view, (280, 80), (320, 320))  # the two right-hand anchors
    assert len(window.tools["direct"].sel) == 2
    drag(view, (300, 100), (400, 100))
    assert approx(p.bounds(), (100, 100, 400, 300))
    click(view, (100, 100))
    window.delete_selection()  # deletes the anchor, not the object
    assert items(tab) == [p] and len(anchors(p)) == 3
    click(view, (400, 100), Qt.AltModifier)  # corner -> smooth
    a = anchors(p)[0]
    assert a.smooth and a.hin and a.hout
    hx, hy = a.hout
    drag(view, (hx, hy), (hx + 30, hy + 40))  # move one handle; the other stays opposite
    a = anchors(p)[0]
    v1 = (a.hout[0] - a.x, a.hout[1] - a.y)
    v2 = (a.hin[0] - a.x, a.hin[1] - a.y)
    assert abs(v1[0] * v2[1] - v1[1] * v2[0]) < 1e-3 * (abs(v1[0]) + abs(v1[1])) * (abs(v2[0]) + abs(v2[1]))
    click(view, (400, 100), Qt.AltModifier)  # smooth -> corner
    assert anchors(p)[0].hin is None and anchors(p)[0].hout is None


def test_direct_selection_converts_shapes_to_paths(env):
    window, tab, view = env
    r = tab.doc.add(RectItem(x=100, y=100, w=100, h=100, fill=Color(9, 9, 9), name="box"))
    tab.scene.rebuild()
    window.set_tool("direct")
    click(view, (150, 150))
    click(view, (200, 200))
    drag(view, (200, 200), (260, 260))
    (p,) = items(tab)
    assert isinstance(p, PathItem) and p.name == "box" and p.fill == Color(9, 9, 9)
    assert approx(p.bounds(), (100, 100, 260, 260)) and window.selection() == [p]
    window.undo()
    assert items(tab) == [r]


def test_add_delete_convert_anchor_tools(env):
    window, tab, view = env
    p = make_path(tab, window)
    window.set_tool("add_anchor")
    click(view, (200, 200))  # selects the path
    click(view, (200, 100))  # on the top edge
    assert len(anchors(p)) == 5 and approx(anchors(p)[1].p, (200, 100))
    window.set_tool("delete_anchor")
    click(view, (200, 100))
    assert len(anchors(p)) == 4
    window.set_tool("convert")
    drag(view, (300, 100), (340, 100))
    a = anchors(p)[1]
    assert a.smooth and approx(a.hout, (340, 100)) and approx(a.hin, (260, 100))
    click(view, (300, 100))
    assert anchors(p)[1].hout is None
    for _ in range(4):
        window.undo()
    assert len(anchors(p)) == 4 and all(a.hin is None for a in anchors(p))
