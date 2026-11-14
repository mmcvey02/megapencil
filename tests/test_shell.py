"""Milestone 1: window shell, artboard, zoom and pan (headless)."""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from megapencil.ui.rulers import tick_step


def test_window_shell(window, qapp):
    assert window.windowTitle().endswith("MegaPencil")
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert menus == ["File", "Edit", "Object", "Type", "Select", "View", "Window", "Help"]
    assert window.toolbox.isVisible() and window.controlbar.isVisible()
    assert window.tab is not None and window.tab_widget.count() == 1
    assert window.tab.hruler.isVisible() and window.tab.vruler.isVisible()
    assert not qapp.windowIcon().isNull()


def test_artboard_is_white_on_gray(window, qapp):
    view = window.tab.view
    view.fit_artboard()
    qapp.processEvents()
    img = view.viewport().grab().toImage()
    center = view.to_view(QPointF(400, 300)).toPoint()
    outside = view.to_view(QPointF(-30, -30)).toPoint()
    assert img.pixelColor(center) == QColor("white")
    assert img.pixelColor(outside) == QColor("#535353")


def test_zoom_commands_and_anchor(window, qapp):
    view = window.tab.view
    view.actual_size()
    assert view.zoom == 1.0 and window.zoom_label.text() == "100%"
    view.zoom_in()
    assert abs(view.zoom - 1.25) < 1e-9 and window.zoom_label.text() == "125%"
    anchor = QPointF(300, 200)
    before = view.to_scene(anchor)
    view.set_zoom(3.0, anchor)
    after = view.to_scene(anchor)
    assert abs(before.x() - after.x()) < 1 and abs(before.y() - after.y()) < 1
    view.set_zoom(1e9)
    assert view.zoom == 64.0
    view.fit_artboard()
    tl, br = view.to_view(QPointF(0, 0)), view.to_view(QPointF(800, 600))
    assert tl.x() >= 0 and tl.y() >= 0 and br.x() <= view.viewport().width() and br.y() <= view.viewport().height()


def test_pan_with_hand_tool_and_space(window, qapp):
    view = window.tab.view
    view.actual_size()
    window.set_tool("hand")
    assert window.tool_label.text() == "Hand Tool"
    vp = view.viewport()
    start = view.to_scene(QPointF(200, 200))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(200, 200))
    QTest.mouseMove(vp, QPoint(260, 230))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(260, 230))
    moved = view.to_scene(QPointF(260, 230))
    assert abs(moved.x() - start.x()) < 1.5 and abs(moved.y() - start.y()) < 1.5

    window.set_tool("zoom")
    view.setFocus()
    QTest.keyPress(view, Qt.Key_Space)
    start = view.to_scene(QPointF(300, 300))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(300, 300))
    QTest.mouseMove(vp, QPoint(250, 340))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(250, 340))
    QTest.keyRelease(view, Qt.Key_Space)
    moved = view.to_scene(QPointF(250, 340))
    assert abs(moved.x() - start.x()) < 1.5 and abs(moved.y() - start.y()) < 1.5
    assert view.zoom == 1.0  # space-drag panned instead of zooming


def test_zoom_tool_click(window, qapp):
    view = window.tab.view
    view.actual_size()
    window.set_tool("zoom")
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(300, 300))
    assert abs(view.zoom - 1.5) < 1e-9
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.AltModifier, QPoint(300, 300))
    assert abs(view.zoom - 1.0) < 1e-9


def test_guides_from_ruler_are_undoable(window, qapp):
    tab = window.tab
    view = tab.view
    view.begin_guide_drag("h")
    view.update_guide_drag(QPointF(100, 150))
    view.finish_guide_drag()
    assert len(tab.doc.guides) == 1 and tab.doc.guides[0][0] == "h"
    assert abs(tab.doc.guides[0][1] - view.to_scene(QPointF(100, 150)).y()) < 0.01
    assert tab.is_modified() and tab.title().endswith("*")
    window.undo()
    assert tab.doc.guides == ()


def test_theme_switch_and_tick_step(window, qapp):
    window.set_theme("light")
    assert window.tab.scene.pasteboard_color == QColor("#c8c8c8")
    window.set_theme("dark")
    assert tick_step(1.0) == 100 and tick_step(10.0) == 10 and tick_step(0.1) == 1000


def test_tabs_and_shortcut_list(window, qapp):
    window.new_document(300, 200)
    assert window.tab_widget.count() == 2 and window.tab.doc.width == 300
    rows = window.shortcut_rows()
    assert ("File", "Save", "Ctrl+S") in rows and any(r[1] == "Hand" and r[2] == "H" for r in rows)
    assert window.close_tab(1) and window.tab_widget.count() == 1
