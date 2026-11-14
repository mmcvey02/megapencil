"""Milestones 8-11: text, file I/O, export, autosave, booleans, gradients, preferences."""
import os

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from helpers import approx, click
from megapencil.model import svgio
from megapencil.model.items import EllipseItem, PathItem, RectItem, TextItem
from megapencil.model.paint import Color, Gradient
from megapencil.ui.autosave import AutosaveManager
from megapencil.ui.export import export_pdf, export_png, render_image
from megapencil.ui.panels.stroke import parse_dash


@pytest.fixture
def env(window, qapp):
    tab = window.tab
    tab.view.actual_size()
    return window, tab, tab.view


# -- text ---------------------------------------------------------------
def test_text_tool_creates_and_edits_point_text(env, qapp):
    window, tab, view = env
    window.state.set(font_family="DejaVu Sans", font_size=40.0, fill=Color(0, 0, 0))
    window.set_tool("text")
    click(view, (100, 200))
    ed = tab.text_editor
    assert ed is not None
    QTest.keyClicks(ed, "Hello")
    QTest.keyClick(ed, Qt.Key_Return, Qt.ControlModifier)
    assert tab.text_editor is None
    (t,) = list(tab.doc.all_items())
    assert isinstance(t, TextItem) and t.text == "Hello" and t.font_size == 40 and approx((t.x, t.y), (100, 200))
    x0, y0, x1, y1 = t.bounds()
    assert 95 < x0 < 110 and 160 < y0 < 175 and x1 - x0 > 80 and y1 <= 201

    click(view, (x0 + 20, (y0 + y1) / 2))  # click existing text: edit it
    ed = tab.text_editor
    assert ed is not None and ed.toPlainText() == "Hello"
    ed.setPlainText("Hello\nWorld")
    ed.commit()
    assert t.text == "Hello\nWorld" and t.bounds()[3] > 230
    window.undo()
    assert t.text == "Hello"

    click(view, (500, 400))  # empty text is discarded
    tab.text_editor.cancel()
    click(view, (500, 400))
    tab.text_editor.commit()
    assert len(list(tab.doc.all_items())) == 1


def test_font_changes_and_create_outlines(env):
    window, tab, view = env
    t = tab.doc.add(TextItem(x=100, y=200, text="Ag", font_size=50))
    tab.scene.rebuild()
    tab.scene.set_selection([t])
    w0 = t.bounds()[2] - t.bounds()[0]
    window.apply_style("font_size", 100.0)
    assert abs((t.bounds()[2] - t.bounds()[0]) / w0 - 2) < 0.1
    window.apply_style("font_family", "DejaVu Serif")
    window.toggle_text_flag("bold")
    assert t.font_family == "DejaVu Serif" and t.bold
    before = t.bounds()
    window.create_outlines()
    (p,) = list(tab.doc.all_items())
    assert isinstance(p, PathItem) and len(p.path.subpaths) >= 3  # A (2 contours) + g
    assert any(a.hin or a.hout for s in p.path.subpaths for a in s.anchors)
    assert approx(p.bounds(), before, 1e-6) and p.fill == t.fill and window.selection() == [p]
    window.undo()
    assert list(tab.doc.all_items()) == [t]


# -- file I/O -----------------------------------------------------------
def build(tab):
    doc = tab.doc
    doc.add(RectItem(x=0, y=0, w=400, h=600, fill=Color(255, 0, 0)))
    doc.add(EllipseItem(cx=600, cy=300, rx=100, ry=100, fill=Color(0, 0, 255), stroke=Color(0, 0, 0), stroke_width=6))
    doc.add(TextItem(x=420, y=80, text="MegaPencil", font_size=32))
    tab.scene.rebuild()


def test_save_open_roundtrip_and_recent_files(env, tmp_path):
    window, tab, view = env
    build(tab)
    window.tab.push(__import__("megapencil").commands.PropertyCommand(tab.doc, [(tab.doc.layers[0], "name", "Art")]))
    path = str(tmp_path / "drawing.svg")
    assert tab.is_modified()
    assert window.save_as(tab, path)
    assert not tab.is_modified() and tab.title() == "drawing.svg" and window.settings.recent_files() == [path]
    text = open(path, encoding="utf-8").read()
    window.close_tab(0)
    tab2 = window.open_file(path)
    assert tab2 is not None and svgio.dumps(tab2.doc) == text and tab2.doc.layers[0].name == "Art"
    assert window.open_file(path) is tab2  # already open: just focus it
    assert window.open_file(str(tmp_path / "missing.svg")) is None
    bad = tmp_path / "bad.svg"
    bad.write_text("<svg><not closed")
    assert window.open_file(str(bad)) is None


def test_export_png_and_pdf(env, tmp_path):
    window, tab, view = env
    build(tab)
    png = str(tmp_path / "out.png")
    assert export_png(tab.doc, png, scale=0.5, transparent=True)
    img = QImage(png)
    assert (img.width(), img.height()) == (400, 300)
    assert img.pixelColor(100, 150) == QColor(255, 0, 0)
    assert img.pixelColor(300, 150) == QColor(0, 0, 255)
    assert img.pixelColor(390, 290).alpha() == 0
    opaque = render_image(tab.doc, 2.0, transparent=False)
    assert opaque.width() == 1600 and opaque.pixelColor(1580, 1180) == QColor("white")
    pdf = str(tmp_path / "out.pdf")
    assert export_pdf(tab.doc, pdf)
    data = open(pdf, "rb").read()
    assert data.startswith(b"%PDF") and len(data) > 1000
    assert len(tab.doc.listeners) == 1  # export scenes detach themselves


def test_autosave_and_recovery(env, qapp):
    window, tab, view = env
    assert window.autosave.run() == 0  # nothing modified
    window.set_tool("rect")
    from helpers import drag

    drag(view, (100, 100), (300, 200))
    assert window.autosave.run() == 1 and window.autosave.run() == 0
    pending = AutosaveManager.pending()
    assert len(pending) == 1 and pending[0]["name"] == tab.name()
    # simulate a crash: a second window starts while the autosave is still on disk
    from megapencil.ui.mainwindow import MainWindow

    other = MainWindow(interactive=False)
    assert other.recover_autosaves() == 1
    rec = other.tab
    assert len(list(rec.doc.all_items())) == 1 and rec.is_modified() and "recovered" in rec.name()
    assert AutosaveManager.pending() == []
    other.close()
    other.deleteLater()
    # a clean save removes the autosave copy
    drag(view, (400, 100), (500, 200))
    assert window.autosave.run() == 1
    window.close_tab(0)
    assert AutosaveManager.pending() == []


def test_preferences_and_settings(env):
    window, tab, view = env
    s = window.settings
    assert s.get("theme") == "dark" and s.get("nudge") == 1.0 and s.get("autosave_enabled") is True
    s.set("nudge", 2.5)
    s.set("autosave_enabled", False)
    window.autosave.configure()
    assert s.get("nudge") == 2.5 and not window.autosave.timer.isActive()
    from megapencil.ui.dialogs import PreferencesDialog

    dlg = PreferencesDialog(window, s)
    dlg.theme.setCurrentText("light")
    dlg.autosave.setChecked(True)
    dlg.interval.setValue(30)
    dlg.apply()
    window.autosave.configure()
    assert s.get("theme") == "light" and window.autosave.timer.interval() == 30000
    for i in range(15):
        s.add_recent(f"/tmp/f{i}.svg")
    assert len(s.recent_files()) == 10 and s.recent_files()[0].endswith("f14.svg")
    s.clear_recent()
    assert s.recent_files() == []


# -- booleans / gradients -----------------------------------------------
def two_shapes(tab):
    a = tab.doc.add(RectItem(x=100, y=100, w=200, h=200, fill=Color(255, 0, 0), stroke=Color(0, 0, 0)))
    b = tab.doc.add(EllipseItem(cx=300, cy=200, rx=100, ry=100, fill=Color(0, 0, 255)))
    tab.scene.rebuild()
    tab.scene.set_selection([a, b])
    return a, b


@pytest.mark.parametrize("op,box,style", [("union", (100, 100, 400, 300), "front"),
                                          ("subtract", (100, 100, 300, 300), "back"),
                                          ("intersect", (200, 100, 300, 300), "front"),
                                          ("exclude", (100, 100, 400, 300), "front")])
def test_boolean_operations(env, op, box, style):
    window, tab, view = env
    a, b = two_shapes(tab)
    window.boolean(op)
    (p,) = list(tab.doc.all_items())
    assert isinstance(p, PathItem) and window.selection() == [p]
    assert approx(p.bounds(), box, 0.2)
    assert p.fill == (b.fill if style == "front" else a.fill)
    g = tab.scene.graphics[id(p)]
    inside_both = g.path().contains(QPointF(250, 200))
    assert inside_both == (op in ("union", "intersect"))
    window.undo()
    assert list(tab.doc.all_items()) == [a, b]


def test_gradient_fill_via_color_panel(env, qapp):
    window, tab, view = env
    r = tab.doc.add(RectItem(x=100, y=100, w=400, h=200, fill=Color(255, 0, 0)))
    tab.scene.rebuild()
    tab.scene.set_selection([r])
    panel = window.panels["panel_color"]
    window.state.set(target="fill")
    panel.type.setCurrentIndex(2)  # linear
    assert isinstance(r.fill, Gradient) and r.fill.kind == "linear" and r.fill.stops[0].color == Color(255, 0, 0)
    panel.stop.setCurrentIndex(1)
    panel.set_color(Color(0, 0, 255))
    qapp.processEvents()
    img = view.viewport().grab().toImage()
    left = img.pixelColor(view.to_view(QPointF(110, 200)).toPoint())
    right = img.pixelColor(view.to_view(QPointF(490, 200)).toPoint())
    assert left.red() > 220 and left.blue() < 40 and right.blue() > 220 and right.red() < 40
    panel.angle.setValue(90)
    assert abs(r.fill.angle() - 90) < 1e-6
    panel._add_stop()
    assert len(r.fill.stops) == 3
    panel.type.setCurrentIndex(3)  # radial
    assert r.fill.kind == "radial" and len(r.fill.stops) == 3
    qapp.processEvents()
    img = view.viewport().grab().toImage()
    centre = img.pixelColor(view.to_view(QPointF(300, 200)).toPoint())
    assert centre.red() > 200
    doc2 = svgio.loads(svgio.dumps(tab.doc))  # gradients survive save / load
    assert doc2.layers[0].children[0].fill == r.fill
    panel.type.setCurrentIndex(0)
    assert r.fill is None
    panel.boxes["R"].setValue(10)  # editing a channel turns 'None' back into a colour
    assert r.fill == Color(10, 0, 0)
    panel.hex.setText("#00FF80")
    panel._hex_edited()
    assert r.fill == Color(0, 255, 128)


def test_stroke_panel(env):
    window, tab, view = env
    r = tab.doc.add(RectItem(x=100, y=100, w=100, h=100, stroke=Color(0, 0, 0)))
    tab.scene.rebuild()
    tab.scene.set_selection([r])
    panel = window.panels["panel_stroke"]
    panel.weight.setValue(8)
    panel.cap.setCurrentIndex(1)
    panel.join.setCurrentIndex(2)
    panel.dash.setText("8, 4")
    panel._dash_edited()
    assert (r.stroke_width, r.stroke_cap, r.stroke_join, r.dash) == (8, "round", "bevel", (8.0, 4.0))
    assert parse_dash("") == () and parse_dash("x") is None and parse_dash("0 0") is None
    assert tab.scene.graphics[id(r)].pen().dashPattern() == [1.0, 0.5]
