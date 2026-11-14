"""Milestones 5-7: layers panel, arrange, group, align, duplicate, clipboard, undo."""
import pytest
from PySide6.QtCore import Qt

from helpers import approx, click, drag
from megapencil.model import svgio
from megapencil.model.items import GroupItem, RectItem
from megapencil.model.paint import Color


@pytest.fixture
def env(window, qapp):
    tab = window.tab
    tab.view.actual_size()
    rects = [tab.doc.add(RectItem(x=x, y=y, w=w, h=40, fill=Color(200, 0, 0)))
             for x, y, w in ((50, 50, 100), (200, 80, 60), (400, 120, 80))]
    tab.scene.rebuild()
    window.set_tool("select")
    return window, tab, tab.view, rects


def row_for(panel, layer):
    for i in range(panel.tree.topLevelItemCount()):
        it = panel.tree.topLevelItem(i)
        if it.data(2, Qt.UserRole) is layer:
            return it
    raise AssertionError("layer row missing")


def test_layers_panel_full_cycle(env, qapp):
    window, tab, view, (a, b, c) = env
    panel = window.panels["panel_layers"]
    doc = tab.doc
    base = doc.layers[0]
    top = panel.add_layer()
    qapp.processEvents()
    assert doc.layers == [base, top] and tab.scene.active_layer is top and top.name == "Layer 2"
    assert panel.tree.topLevelItemCount() == 2 and panel.tree.topLevelItem(0).text(2) == "Layer 2"

    window.set_tool("rect")
    drag(view, (300, 300), (360, 360))
    assert len(top.children) == 1 and len(base.children) == 3

    row_for(panel, top).setText(2, "Sketch")  # rename (in-place edit)
    assert top.name == "Sketch"
    panel._clicked(row_for(panel, top), 0)  # hide
    assert not top.visible and not tab.scene.layer_graphics[id(top)].isVisible()
    window.set_tool("select")
    click(view, (330, 330))
    assert window.selection() == []  # hidden layers cannot be hit
    panel._clicked(row_for(panel, top), 0)
    panel._clicked(row_for(panel, top), 1)  # lock
    assert top.locked
    click(view, (330, 330))
    assert window.selection() == []
    window.set_tool("rect")
    drag(view, (500, 300), (560, 360))  # active layer is locked
    assert len(top.children) == 1
    panel._clicked(row_for(panel, top), 1)

    panel.opacity.setValue(40)
    assert top.opacity == 0.4 and abs(tab.scene.layer_graphics[id(top)].opacity() - 0.4) < 1e-9
    panel.move_layer(-1)
    assert doc.layers == [top, base]
    assert tab.scene.layer_graphics[id(top)].zValue() < tab.scene.layer_graphics[id(base)].zValue()
    panel.delete_layer()
    assert doc.layers == [base] and tab.scene.active_layer is base
    panel.delete_layer()  # the last layer stays
    assert doc.layers == [base]
    while tab.stack.canUndo():
        tab.stack.undo()
    assert doc.layers == [base] and len(base.children) == 3 and base.opacity == 1.0


def test_arrange_commands(env):
    window, tab, view, (a, b, c) = env
    layer = tab.doc.layers[0]
    tab.scene.set_selection([a])
    window.arrange("front")
    assert layer.children == [b, c, a]
    assert tab.scene.graphics[id(a)].zValue() > tab.scene.graphics[id(c)].zValue()
    window.arrange("backward")
    assert layer.children == [b, a, c]
    window.arrange("back")
    assert layer.children == [a, b, c]
    window.arrange("forward")
    assert layer.children == [b, a, c]


def test_group_ungroup_select_and_move(env):
    window, tab, view, (a, b, c) = env
    tab.scene.set_selection([a, b])
    window.group()
    (g,) = window.selection()
    assert isinstance(g, GroupItem) and tab.doc.layers[0].children == [g, c]
    click(view, (700, 500))
    click(view, (100, 70))  # clicking a member selects the group
    assert window.selection() == [g]
    drag(view, (100, 70), (120, 170))
    assert approx(a.bounds(), (70, 150, 170, 190)) and approx(b.bounds(), (220, 180, 280, 220))
    window.ungroup()
    assert window.selection() == [a, b] and tab.doc.layers[0].children == [a, b, c]
    assert approx(a.bounds(), (70, 150, 170, 190))


def test_align_and_distribute_panel(env):
    window, tab, view, (a, b, c) = env
    panel = window.panels["panel_align"]
    window.select_all()
    panel.align("top")
    assert [it.bounds()[1] for it in (a, b, c)] == [50, 50, 50]
    panel.distribute("hspace")
    gaps = [b.bounds()[0] - a.bounds()[2], c.bounds()[0] - b.bounds()[2]]
    assert abs(gaps[0] - gaps[1]) < 1e-6
    tab.scene.set_selection([a])
    panel.relative.setCurrentText("Artboard")
    panel.align("hcenter")
    panel.align("vcenter")
    assert approx(a.bounds(), (350, 280, 450, 320), 1e-6)
    window.undo()
    window.undo()
    assert approx(a.bounds(), (50, 50, 150, 90), 1e-6)


def test_duplicate_copy_paste_cut(env):
    window, tab, view, (a, b, c) = env
    tab.scene.set_selection([a])
    window.duplicate()
    (d,) = window.selection()
    assert d is not a and approx(d.bounds(), (60, 60, 160, 100), 1e-6) and len(list(tab.doc.all_items())) == 4
    tab.scene.set_selection([b, c])
    window.copy()
    window.paste()
    pasted = window.selection()
    assert len(pasted) == 2 and approx(pasted[0].bounds(), (210, 90, 270, 130), 1e-6)
    window.paste(in_place=True)
    assert approx(window.selection()[0].bounds(), b.bounds(), 1e-6)
    tab.scene.set_selection([a])
    window.cut()
    assert not tab.doc.contains(a)
    other = window.new_document(400, 300)  # paste into another document
    window.paste()
    assert len(list(other.doc.all_items())) == 1


def test_every_edit_is_undoable(env, qapp):
    """Run a long, mixed editing session, then undo everything and redo everything."""
    window, tab, view, (a, b, c) = env
    start = svgio.dumps(tab.doc)
    layers = window.panels["panel_layers"]
    align = window.panels["panel_align"]

    window.set_tool("ellipse")
    drag(view, (500, 300), (600, 380))
    window.set_tool("pen")
    for p in ((100, 400), (200, 450), (150, 520)):
        click(view, p)
    window.set_tool("select")
    click(view, (100, 70))
    window.apply_style("fill", Color(0, 0, 255))
    window.apply_style("stroke_width", 5.0)
    window.apply_style("opacity", 0.5)
    window.apply_geometry(60, 60, 150, 50)
    drag(view, (100, 80), (140, 100))
    window.select_all()
    align.align("left")
    window.copy()
    window.group()
    window.duplicate()
    window.ungroup()
    window.arrange("back")
    layers.add_layer()
    window.paste()
    window.select_all()
    window.boolean("union")
    window.convert_to_path()
    tab.view.begin_guide_drag("v")
    tab.view.update_guide_drag(tab.view.to_view(__import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(120, 100)))
    tab.view.finish_guide_drag()
    window.set_flag_all("visible", True)
    window.select_all()
    window.delete_selection()

    end = svgio.dumps(tab.doc)
    steps = tab.stack.count()
    assert steps >= 16 and end != start
    while tab.stack.canUndo():
        window.undo()
    assert svgio.dumps(tab.doc) == start and not tab.is_modified()
    while tab.stack.canRedo():
        window.redo()
    assert svgio.dumps(tab.doc) == end
