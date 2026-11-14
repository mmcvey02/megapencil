import math

import pytest

from megapencil.model import ops
from megapencil.model.boolean import boolean_op
from megapencil.model.geometry import (Transform, constrain_angle, cubic_bounds, cubic_point, cubic_split,
                                       flatten_cubic, nearest_on_cubic)
from megapencil.model.items import Document, EllipseItem, GroupItem, LineItem, PathItem, RectItem
from megapencil.model.paint import Color, Gradient, GradientStop
from megapencil.model.path import Anchor, PathData, SubPath, ellipse_path, rect_path


def approx(a, b, eps=1e-6):
    return all(abs(x - y) < eps for x, y in zip(a, b))


# -- transforms ---------------------------------------------------------
def test_transform_compose_and_invert():
    t = Transform.translation(10, 5).mul(Transform.rotation(90)).mul(Transform.scaling(2, 3))
    assert approx(t.map(1, 0), (10, 7))
    assert approx(t.inverted().map(*t.map(3, 4)), (3, 4))
    assert t.mul(t.inverted()).is_identity(1e-9)


def test_transform_about_point_and_parse():
    assert approx(Transform.rotation(180, 5, 5).map(0, 0), (10, 10))
    assert approx(Transform.scaling(2, 2, 10, 10).map(10, 10), (10, 10))
    t = Transform.parse("translate(10,20) scale(2) rotate(90)")
    assert approx(t.map(1, 0), (10, 22))
    assert approx(Transform.parse(t.to_svg()), t)
    assert Transform.parse("rotate(90 5 5)") == Transform.rotation(90, 5, 5)


# -- bezier math --------------------------------------------------------
CURVE = ((0, 0), (0, 100), (100, 100), (100, 0))


def test_cubic_split_matches_curve():
    left, right = cubic_split(*CURVE, 0.3)
    assert approx(left[3], cubic_point(*CURVE, 0.3))
    assert approx(cubic_point(*left, 0.5), cubic_point(*CURVE, 0.15))
    assert approx(cubic_point(*right, 0.5), cubic_point(*CURVE, 0.65))


def test_cubic_bounds_uses_extrema():
    assert approx(cubic_bounds(*CURVE), (0, 0, 100, 75))


def test_flatten_and_nearest():
    pts = flatten_cubic(*CURVE, tol=0.01)
    assert pts[-1] == (100, 0) and len(pts) > 10
    t, d = nearest_on_cubic(*CURVE, 50, 80)
    assert abs(t - 0.5) < 1e-3 and abs(d - 5) < 1e-3


def test_constrain_angle():
    assert approx(constrain_angle(10, 1), (math.hypot(10, 1), 0))
    x, y = constrain_angle(10, 9)
    assert abs(x - y) < 1e-9


# -- paths --------------------------------------------------------------
def test_path_svg_roundtrip():
    d = "M10 10 L50 10 C60 10 70 20 70 30 L70 60 Z M0 0 L5 5"
    p = PathData.from_svg(d)
    assert len(p.subpaths) == 2 and p.subpaths[0].closed and not p.subpaths[1].closed
    assert PathData.from_svg(p.to_svg()) == p


def test_path_relative_and_shorthand_commands():
    p = PathData.from_svg("m10,10 h20 v20 h-20 z")
    assert [a.p for a in p.subpaths[0].anchors] == [(10, 10), (30, 10), (30, 30), (10, 30)]
    q = PathData.from_svg("M0 0 Q50 100 100 0 T200 0")
    assert approx(q.bounds(), (0, -50, 200, 50))
    s = PathData.from_svg("M0 0 C0 50 50 50 50 0 S100 -50 100 0")
    assert s.subpaths[0].anchors[1].smooth


def test_path_arc_is_circular():
    p = PathData.from_svg("M100 50 A50 50 0 1 1 0 50 A50 50 0 1 1 100 50 Z")
    assert approx(p.bounds(), (0, 0, 100, 100), 1e-3)
    for pts, _ in p.flatten(0.01):
        assert all(abs(math.hypot(x - 50, y - 50) - 50) < 0.05 for x, y in pts)
    compact = PathData.from_svg("M0 0a5 5 0 0110 0")
    assert approx(compact.bounds(), (0, -5, 10, 0), 1e-3)


def test_closed_curve_merges_duplicate_end_anchor():
    p = PathData.from_svg("M0 0 C10 0 20 10 20 20 C20 30 0 10 0 0 Z")
    s = p.subpaths[0]
    assert len(s.anchors) == 2 and s.anchors[0].hin == (0, 10)


def test_insert_anchor_preserves_shape():
    p = PathData([SubPath([Anchor(0, 0, hout=(0, 100)), Anchor(100, 0, hin=(100, 100))])])
    q = p.insert_anchor(0, 0, 0.5)
    assert len(q.subpaths[0].anchors) == 3 and len(p.subpaths[0].anchors) == 2
    assert approx(q.subpaths[0].anchors[1].p, (50, 75))
    assert approx(q.bounds(), p.bounds())
    line = PathData.from_polygon([(0, 0), (10, 0)], closed=False).insert_anchor(0, 0, 0.25)
    assert line.subpaths[0].anchors[1].p == (2.5, 0)


def test_delete_anchor():
    p = rect_path(0, 0, 10, 10)
    q = p.delete_anchor(0, 0)
    assert len(q.subpaths[0].anchors) == 3
    assert PathData.from_polygon([(0, 0), (1, 1)], False).delete_anchor(0, 0).is_empty()


def test_nearest_segment():
    si, seg, t, d = rect_path(0, 0, 100, 50).nearest_segment(101, 25)
    assert (si, seg) == (0, 1) and abs(t - 0.5) < 1e-6 and abs(d - 1) < 1e-6


def test_shape_paths():
    assert approx(rect_path(5, 5, 20, 10, rx=3).bounds(), (5, 5, 25, 15))
    assert len(rect_path(0, 0, 20, 10, rx=3).subpaths[0].anchors) == 8
    assert approx(ellipse_path(50, 50, 30, 20).bounds(), (20, 30, 80, 70), 1e-6)


# -- paint --------------------------------------------------------------
def test_color_parse():
    assert Color.parse("#f00") == Color(255, 0, 0)
    assert Color.parse("rgb(0, 128, 255)") == Color(0, 128, 255)
    assert Color.parse("rgba(0,0,0,0.5)").a == 0.5
    assert Color.parse("navy") == Color(0, 0, 128)
    assert Color.parse("none") is None and Color.parse("bogus") is None
    assert Color(18, 52, 86).to_hex() == "#123456"


def test_gradient_angle():
    g = Gradient.linear([GradientStop(0, Color(0, 0, 0)), GradientStop(1, Color(255, 255, 255))], 90)
    assert abs(g.angle() - 90) < 1e-9 and hash(g)


# -- items / document ---------------------------------------------------
def make_doc():
    doc = Document.new(400, 300)
    a = doc.add(RectItem(x=0, y=0, w=10, h=10))
    b = doc.add(RectItem(x=50, y=20, w=20, h=20))
    c = doc.add(EllipseItem(cx=200, cy=100, rx=10, ry=30))
    return doc, a, b, c


def test_bounds_with_transform_and_groups():
    r = RectItem(x=0, y=0, w=10, h=20, transform=Transform.translation(5, 5))
    assert r.bounds() == (5, 5, 15, 25)
    g = GroupItem(children=[r], transform=Transform.scaling(2))
    assert r.parent is g and approx(g.bounds(), (10, 10, 30, 50))
    assert approx(LineItem(x1=0, y1=0, x2=3, y2=4).bounds(), (0, 0, 3, 4))


def test_clone_is_independent():
    g = GroupItem(children=[RectItem(w=5, h=5)], name="g")
    c = g.clone()
    assert c.id != g.id and c.children[0] is not g.children[0] and c.children[0].parent is c


def test_to_path_item_keeps_identity():
    r = RectItem(x=1, y=2, w=3, h=4, fill=Color(1, 2, 3), name="r")
    p = r.to_path_item()
    assert isinstance(p, PathItem) and p.id == r.id and p.fill == r.fill and p.bounds() == r.bounds()


def test_apply_world_inside_group():
    r = RectItem(x=0, y=0, w=10, h=10)
    GroupItem(children=[r], transform=Transform.scaling(2))
    r.transform = ops.apply_world(r, Transform.translation(10, 0))
    assert approx(r.bounds(), (10, 0, 30, 20))


def test_align_and_distribute():
    doc, a, b, c = make_doc()
    assert ops.align([a, b, c], "left") == {b: (-50, 0), c: (-190, 0)}
    assert ops.align([a], "hcenter", ref=(0, 0, 400, 300)) == {a: (195, 0)}
    assert ops.align([a, b], "bottom")[a] == (0, 30)
    d = ops.distribute([a, b, c], "hcenters")
    assert d == {b: (42.5, 0.0)}
    d = ops.distribute([a, b, c], "hspace")
    assert approx(d[b], (40.0, 0.0))  # gaps become equal: (210 - 50) / 2 = 80, so b.x = 90
    with pytest.raises(ValueError):
        ops.align([a], "nope")


def test_arrange():
    doc, a, b, c = make_doc()
    layer = doc.layers[0]
    assert ops.arrange([a], "front") == [(layer, [b, c, a])]
    assert ops.arrange([c], "backward") == [(layer, [a, c, b])]
    assert ops.arrange([a, b], "forward") == [(layer, [c, a, b])]
    assert ops.arrange([c], "front") == []


def test_doc_contains_and_iteration():
    doc, a, b, c = make_doc()
    assert doc.contains(a) and not doc.contains(RectItem())
    assert list(doc.all_items()) == [a, b, c]


# -- boolean ------------------------------------------------------------
def area(path):
    total = 0.0
    for pts, _ in path.flatten():
        s = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            s += x0 * y1 - x1 * y0
        total += s / 2
    return abs(total)


def test_boolean_ops_areas():
    a, b = rect_path(0, 0, 10, 10), rect_path(5, 5, 10, 10)
    assert abs(area(boolean_op([a, b], "union")) - 175) < 0.01
    assert abs(area(boolean_op([a, b], "intersect")) - 25) < 0.01
    assert abs(area(boolean_op([a, b], "subtract")) - 75) < 0.01
    assert abs(area(boolean_op([a, b], "exclude")) - 150) < 0.01
    assert boolean_op([a, rect_path(50, 50, 5, 5)], "intersect").is_empty()


def test_boolean_circle_hole():
    ring = boolean_op([ellipse_path(0, 0, 10, 10), ellipse_path(0, 0, 5, 5)], "subtract")
    assert len(ring.subpaths) == 2
    assert abs(area(ring) - math.pi * 75) < 1.0
