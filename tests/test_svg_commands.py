from PySide6.QtGui import QUndoStack

from megapencil import commands as C
from megapencil.model import svgio
from megapencil.model.geometry import Transform
from megapencil.model.items import (Document, EllipseItem, GroupItem, Layer, LineItem, PathItem, RectItem,
                                    TextItem)
from megapencil.model.paint import Color, Gradient, GradientStop
from megapencil.model.path import PathData


def approx(a, b, eps=1e-3):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def sample_doc():
    doc = Document.new(640, 480)
    doc.guides = (("h", 100.0), ("v", 42.5))
    grad = Gradient.linear([GradientStop(0, Color(255, 0, 0)), GradientStop(1, Color(0, 0, 255, 0.5))], 45)
    doc.add(RectItem(x=10, y=20, w=100, h=50, rx=8, fill=grad, stroke=Color(0, 0, 0), stroke_width=2.5,
                     name="card", dash=(4, 2), stroke_cap="round", stroke_join="bevel"))
    doc.add(EllipseItem(cx=200, cy=100, rx=40, ry=30, fill=Color(0, 200, 0, 0.5), opacity=0.7,
                        transform=Transform.rotation(30, 200, 100)))
    doc.add(LineItem(x1=0, y1=0, x2=50, y2=50, stroke=Color(9, 9, 9), locked=True))
    top = doc.add_layer(Layer("Top", visible=False, locked=True, opacity=0.5))
    p = PathItem(path=PathData.from_svg("M0 0 C10 20 30 20 40 0 L40 40 Z"), fill=Color(1, 2, 3),
                 stroke=Gradient.radial([GradientStop(0, Color(255, 255, 255)), GradientStop(1, Color(0, 0, 0))]))
    t = TextItem(x=5, y=30, text="Hello\nWorld & <more>", font_family="DejaVu Serif", font_size=18, bold=True,
                 italic=True, visible=False)
    doc.add(GroupItem(children=[p, t], transform=Transform.translation(100, 100), name="grp", opacity=0.9), top)
    return doc


def snapshot(doc):
    def item(it):
        d = {k: v for k, v in vars(it).items() if k not in ("parent", "children", "path")}
        if isinstance(it, PathItem):
            d["path"] = it.path.to_svg()
        if isinstance(it, GroupItem):
            d["children"] = [item(c) for c in it.children]
        return d

    def rnd(v):  # SVG output keeps 4 decimals
        if isinstance(v, float):
            return round(v, 3)
        if isinstance(v, dict):
            return {k: rnd(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [rnd(x) for x in v]
        if hasattr(v, "__dataclass_fields__"):
            return rnd(vars(v))
        return v

    return rnd((doc.width, doc.height, doc.guides,
                [(l.id, l.name, l.visible, l.locked, l.opacity, [item(i) for i in l.children]) for l in doc.layers]))


def test_svg_roundtrip_is_lossless():
    doc = sample_doc()
    text = svgio.dumps(doc)
    doc2 = svgio.loads(text)
    assert snapshot(doc2) == snapshot(doc)
    assert svgio.dumps(doc2) == text
    assert 'inkscape:groupmode="layer"' in text and 'inkscape:label="Top"' in text


def test_svg_save_load_file(tmp_path):
    doc = sample_doc()
    f = tmp_path / "a.svg"
    svgio.save(doc, str(f))
    assert snapshot(svgio.load(str(f))) == snapshot(doc)


def test_import_foreign_svg():
    text = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
      width="100mm" height="50mm" viewBox="0 0 200 100">
      <defs>
        <linearGradient id="base"><stop offset="0%" stop-color="red"/><stop offset="100%" style="stop-color:#00f"/></linearGradient>
        <linearGradient id="g" xlink:href="#base" x1="0" y1="0" x2="0" y2="1"/>
      </defs>
      <g style="fill:#ff0000;stroke:blue;stroke-width:2" transform="translate(10 10)">
        <circle cx="10" cy="10" r="5"/>
        <polygon points="0,0 10,0 10,10" fill="url(#g)" stroke="none"/>
        <polyline points="0,0 10,0" style="fill:none"/>
      </g>
      <rect width="20" height="10"/>
      <image href="x.png"/>
    </svg>"""
    doc = svgio.loads(text)
    scale = 100 * 96 / 25.4 / 200
    assert abs(doc.width - 377.953) < 0.01 and len(doc.layers) == 1
    g, rect = doc.layers[0].children
    circle, poly, line = g.children
    assert isinstance(circle, EllipseItem) and circle.fill == Color(255, 0, 0) and circle.stroke == Color(0, 0, 255)
    assert abs(circle.stroke_width - 2 * scale) < 1e-6
    assert approx(circle.bounds(), [v * scale for v in (15, 15, 25, 25)])
    assert isinstance(poly.fill, Gradient) and poly.fill.y2 == 1 and poly.stroke is None
    assert poly.fill.stops[1].color == Color(0, 0, 255)
    assert poly.path.subpaths[0].closed and not line.path.subpaths[0].closed and line.fill is None
    assert rect.fill == Color(0, 0, 0) and rect.stroke is None
    assert doc.import_skipped == 1


# -- commands -----------------------------------------------------------
def setup():
    doc = Document.new()
    a = doc.add(RectItem(x=0, y=0, w=10, h=10))
    b = doc.add(RectItem(x=20, y=0, w=10, h=10))
    events = []
    doc.listeners.append(lambda kind, objs: events.append(kind))
    return doc, a, b, QUndoStack(), events


def test_property_command_undo_redo():
    doc, a, b, stack, events = setup()
    stack.push(C.PropertyCommand(doc, [(a, "fill", Color(1, 1, 1)), (b, "opacity", 0.5)]))
    assert a.fill == Color(1, 1, 1) and b.opacity == 0.5 and events == ["props"]
    stack.undo()
    assert a.fill is None and b.opacity == 1.0
    stack.redo()
    assert a.fill == Color(1, 1, 1)


def test_property_command_merge():
    doc, a, b, stack, _ = setup()
    for v in (0.9, 0.8, 0.7):
        stack.push(C.PropertyCommand(doc, [(a, "opacity", v)], merge_key="drag1"))
    stack.push(C.PropertyCommand(doc, [(a, "opacity", 0.1)], merge_key="drag2"))
    assert stack.count() == 2
    stack.undo()
    assert a.opacity == 0.7
    stack.undo()
    assert a.opacity == 1.0


def test_structure_commands():
    doc, a, b, stack, events = setup()
    layer = doc.layers[0]
    c = RectItem(w=1, h=1)
    stack.push(C.add_items(doc, layer, [c]))
    assert layer.children == [a, b, c] and c.parent is layer and events[-1] == "structure"
    stack.push(C.delete_items(doc, [a, c]))
    assert layer.children == [b]
    stack.push(C.arrange_items(doc, [b], "front") or C.add_layer(doc, Layer("L2")))
    assert len(doc.layers) == 2
    while stack.canUndo():
        stack.undo()
    assert layer.children == [a, b] and len(doc.layers) == 1


def test_group_ungroup_keeps_geometry_and_undoes():
    doc, a, b, stack, _ = setup()
    layer = doc.layers[0]
    l2 = doc.add_layer(Layer("L2"))
    c = doc.add(RectItem(x=50, y=50, w=5, h=5), l2)
    before = [it.bounds() for it in (a, b, c)]
    cmd, g = C.group_items(doc, [c, a])
    stack.push(cmd)
    assert layer.children == [b] and l2.children == [g] and g.children == [a, c] and a.parent is g
    stack.push(C.transform_items(doc, [g], Transform.translation(5, 0)))
    stack.push(C.PropertyCommand(doc, [(g, "opacity", 0.5)]))
    cmd, kids = C.ungroup_items(doc, [g])
    stack.push(cmd)
    assert l2.children == [a, c] and a.parent is l2 and a.opacity == 0.5
    assert approx(a.bounds(), (5, 0, 15, 10))
    while stack.canUndo():
        stack.undo()
    assert layer.children == [a, b] and l2.children == [c] and a.parent is layer
    assert [it.bounds() for it in (a, b, c)] == before and a.opacity == 1.0


def test_move_and_replace():
    doc, a, b, stack, _ = setup()
    stack.push(C.move_items(doc, {a: (3, 4)}))
    assert a.bounds() == (3, 4, 13, 14)
    p = a.to_path_item()
    stack.push(C.replace_item(doc, a, p))
    assert doc.layers[0].children == [p, b] and doc.contains(p) and not doc.contains(a)
    stack.undo()
    assert doc.contains(a)
