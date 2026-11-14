"""Mouse helpers for headless GUI tests (positions in document coordinates)."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest


def vpt(view, x, y):
    return view.to_view(QPointF(x, y)).toPoint()


def drag(view, p0, p1, mods=Qt.NoModifier, steps=4):
    vp = view.viewport()
    a, b = vpt(view, *p0), vpt(view, *p1)
    QTest.mousePress(vp, Qt.LeftButton, mods, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, a + (b - a) * i / steps)
        # QTest.mouseMove carries no modifiers; send them through the tool directly when needed
    _move_with_mods(view, b, mods)
    QTest.mouseRelease(vp, Qt.LeftButton, mods, b)


def _move_with_mods(view, point, mods):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    vp = view.viewport()
    ev = QMouseEvent(QEvent.MouseMove, QPointF(point), QPointF(vp.mapToGlobal(point)), Qt.NoButton, Qt.LeftButton, mods)
    QApplication.sendEvent(vp, ev)


def click(view, p, mods=Qt.NoModifier):
    QTest.mouseClick(view.viewport(), Qt.LeftButton, mods, vpt(view, *p))


def approx(a, b, eps=1.0):
    return all(abs(x - y) <= eps for x, y in zip(a, b))
