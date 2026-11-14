"""Interaction stays smooth with 5,000 objects (generous CI-safe limits)."""
import random
import time

from PySide6.QtCore import QPointF
from PySide6.QtGui import QTransform

from megapencil import commands as C
from megapencil.model.geometry import Transform
from megapencil.model.items import EllipseItem, RectItem
from megapencil.model.paint import Color

N = 5000


def timed(fn, repeat=1):
    t = time.perf_counter()
    for _ in range(repeat):
        fn()
    return (time.perf_counter() - t) / repeat * 1000


def test_5000_objects(window, qapp, capsys):
    tab = window.tab
    view = tab.view
    rnd = random.Random(1)
    for i in range(N):
        x, y = rnd.uniform(0, 760), rnd.uniform(0, 560)
        col = Color(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
        cls = RectItem if i % 2 else EllipseItem
        kw = dict(x=x, y=y, w=30, h=20) if i % 2 else dict(cx=x + 15, cy=y + 10, rx=15, ry=10)
        tab.doc.add(cls(fill=col, stroke=Color(0, 0, 0), **kw))
    results = {}
    results["build scene"] = timed(tab.scene.rebuild)
    view.fit_artboard()
    qapp.processEvents()
    results["repaint (all visible)"] = timed(lambda: (view._invalidate(), view.viewport().grab()), 5)
    results["overlay-only repaint (hover, marquee)"] = timed(lambda: (view.refresh(), view.viewport().grab()), 5)
    results["hit test"] = timed(lambda: tab.scene.item_at(QPointF(400, 300), 3), 20)
    results["select all"] = timed(window.select_all)
    assert len(window.selection()) == N
    items = tab.scene.selection

    def drag_step():
        tab.scene.preview_transform(items, QTransform.fromTranslate(5, 5))
        view._invalidate()
        view.viewport().grab()

    results["move drag frame (all selected)"] = timed(drag_step, 3)
    tab.scene.preview_transform(items, None)

    few = items[:10]
    view.float_items(few)
    view.viewport().grab()  # first frame renders the static picture

    def drag_few():
        tab.scene.preview_transform(few, QTransform.fromTranslate(7, 3))
        view._invalidate()
        view.viewport().grab()

    results["move drag frame (10 selected)"] = timed(drag_few, 5)
    tab.scene.preview_transform(few, None)
    view.unfloat()
    results["commit move"] = timed(lambda: tab.push(C.transform_items(tab.doc, items, Transform.translation(5, 5))))
    results["undo move"] = timed(tab.stack.undo)
    results["zoom"] = timed(lambda: (view.set_zoom(view.zoom * 1.1), view.viewport().grab()), 5)
    results["delete all"] = timed(window.delete_selection)
    results["undo delete"] = timed(tab.stack.undo)
    with capsys.disabled():
        print("\n  5,000 objects (ms): " + ", ".join(f"{k} {v:.0f}" for k, v in results.items()))
    assert results["repaint (all visible)"] < 250
    assert results["overlay-only repaint (hover, marquee)"] < 30
    assert results["move drag frame (all selected)"] < 400
    assert results["move drag frame (10 selected)"] < 30
    assert results["hit test"] < 50
    assert results["zoom"] < 250
    assert max(results.values()) < 3000
