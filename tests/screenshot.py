"""Headless smoke test: start the app, draw a sample document, grab the main window.

    QT_QPA_PLATFORM=offscreen python tests/screenshot.py out.png [dark|light] [tool]
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from megapencil.app import create_app  # noqa: E402
from megapencil.model.geometry import Transform  # noqa: E402
from megapencil.model.items import EllipseItem, Layer, LineItem, PathItem, RectItem, TextItem  # noqa: E402
from megapencil.model.paint import Color, Gradient, GradientStop  # noqa: E402
from megapencil.model.path import PathData  # noqa: E402
from megapencil.ui.mainwindow import MainWindow  # noqa: E402


def sample(doc):
    sky = Gradient.linear([GradientStop(0, Color(59, 42, 122)), GradientStop(1, Color(255, 177, 26))], 90)
    sun = Gradient.radial([GradientStop(0, Color(255, 243, 163)), GradientStop(1, Color(240, 140, 0))])
    doc.layers[0].name = "Background"
    doc.add(RectItem(x=40, y=40, w=720, h=520, rx=24, fill=sky, name="Sky"))
    doc.add(EllipseItem(cx=560, cy=220, rx=90, ry=90, fill=sun, name="Sun"))
    art = doc.add_layer(Layer("Artwork"))
    hills = PathData.from_svg("M40 420 C160 300 260 330 360 400 C460 300 620 300 760 430 L760 536 "
                              "C760 549 749 560 736 560 L64 560 C51 560 40 549 40 536 Z")
    doc.add(PathItem(path=hills, fill=Color(22, 16, 46), name="Hills"), art)
    doc.add(PathItem(path=PathData.from_svg("M120 200 C180 120 260 260 330 170"), stroke=Color(127, 227, 255),
                     stroke_width=6, stroke_cap="round", name="Curve"), art)
    doc.add(LineItem(x1=100, y1=500, x2=700, y2=500, stroke=Color(255, 255, 255, 0.6), stroke_width=2,
                     dash=(12, 8)), art)
    doc.add(RectItem(x=420, y=110, w=90, h=60, fill=Color(255, 111, 145), stroke=Color(255, 255, 255),
                     stroke_width=3, transform=Transform.rotation(-18, 465, 140), name="Card"), art)
    doc.add(TextItem(x=96, y=470, text="MegaPencil", font_family="DejaVu Sans", font_size=64, bold=True,
                     fill=Color(255, 255, 255)), art)
    doc.guides = (("h", 300.0), ("v", 400.0))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "megapencil.png"
    app = create_app(sys.argv[:1])
    win = MainWindow(interactive=False)
    win.set_theme(sys.argv[2] if len(sys.argv) > 2 else "dark")
    win.resize(1400, 900)
    win.show()
    tab = win.new_document(800, 600)
    sample(tab.doc)
    tab.scene.rebuild()
    tab.scene.active_layer = tab.doc.layers[-1]
    win.set_tool(sys.argv[3] if len(sys.argv) > 3 else "select")
    card = next(i for i in tab.doc.all_items() if i.name == ("Curve" if win.tool.name == "direct" else "Card"))
    tab.scene.set_selection([card])
    if win.tool.name == "direct":
        win.tool.select_all_anchors(card)
    for _ in range(5):
        app.processEvents()
    ok = win.grab().save(out)
    print("saved" if ok else "failed", out)
    win.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
