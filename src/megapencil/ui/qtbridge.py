"""Conversions between the pure model and Qt types."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainterPath, QPen, QRadialGradient,
                           QTransform)

from ..model import items as model_items
from ..model.geometry import Transform
from ..model.items import Item, TextItem
from ..model.paint import Color, Gradient
from ..model.path import Anchor, PathData, SubPath

CAPS = {"butt": Qt.FlatCap, "round": Qt.RoundCap, "square": Qt.SquareCap}
JOINS = {"miter": Qt.MiterJoin, "round": Qt.RoundJoin, "bevel": Qt.BevelJoin}


def qtransform(t: Transform) -> QTransform:
    return QTransform(t.a, t.b, t.c, t.d, t.e, t.f)


def qcolor(c: Color | None) -> QColor:
    if c is None:
        return QColor(0, 0, 0, 0)
    return QColor(c.r, c.g, c.b, int(round(c.a * 255)))


def from_qcolor(c: QColor) -> Color:
    return Color(c.red(), c.green(), c.blue(), round(c.alphaF(), 3))


def to_qpath(path: PathData) -> QPainterPath:
    qp = QPainterPath()
    qp.setFillRule(Qt.WindingFill)
    for s in path.subpaths:
        if not s.anchors:
            continue
        qp.moveTo(s.anchors[0].x, s.anchors[0].y)
        for i in range(s.segment_count()):
            p0, c1, c2, p3, curve = s.segment_points(i)
            if curve:
                qp.cubicTo(c1[0], c1[1], c2[0], c2[1], p3[0], p3[1])
            else:
                qp.lineTo(p3[0], p3[1])
        if s.closed:
            qp.closeSubpath()
    return qp


def from_qpath(qp: QPainterPath) -> PathData:
    out = PathData()
    cur: SubPath | None = None
    i, n = 0, qp.elementCount()
    while i < n:
        e = qp.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            cur = SubPath([Anchor(e.x, e.y)])
            out.subpaths.append(cur)
        elif e.type == QPainterPath.ElementType.LineToElement and cur is not None:
            cur.anchors.append(Anchor(e.x, e.y))
        elif e.type == QPainterPath.ElementType.CurveToElement and cur is not None:
            c2, p = qp.elementAt(i + 1), qp.elementAt(i + 2)
            cur.anchors[-1].hout = (e.x, e.y)
            cur.anchors.append(Anchor(p.x, p.y, hin=(c2.x, c2.y)))
            i += 2
        i += 1
    result = PathData()
    for s in out.subpaths:
        a = s.anchors
        if len(a) > 2 and abs(a[0].x - a[-1].x) < 1e-6 and abs(a[0].y - a[-1].y) < 1e-6:
            a[0].hin = a[-1].hin
            a.pop()
            s.closed = True
        if len(a) >= 2:
            result.subpaths.append(s)
    return result


def make_font(family: str, size: float, bold: bool = False, italic: bool = False) -> tuple[QFont, float]:
    """Return (font, scale): the font uses an integer pixel size; scale corrects it."""
    f = QFont(family)
    px = max(1, int(round(size)))
    f.setPixelSize(px)
    f.setBold(bold)
    f.setItalic(italic)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f, size / px


def outline_text(item: TextItem) -> PathData:
    """Glyph outlines of a text item in its local coordinates."""
    font, scale = make_font(item.font_family, item.font_size, item.bold, item.italic)
    qp = QPainterPath()
    for i, line in enumerate(item.text.split("\n")):
        if line:
            qp.addText(QPointF(0, i * 1.2 * item.font_size / scale), font, line)
    t = QTransform()
    t.translate(item.x, item.y)
    t.scale(scale, scale)
    return from_qpath(t.map(qp))


def install_text_outliner() -> None:
    model_items.text_outliner = outline_text


def make_brush(paint, bbox: QRectF, world: QTransform | None = None) -> QBrush:
    """Brush for a paint; gradients are laid out on ``bbox`` (local coords)."""
    if paint is None:
        return QBrush(Qt.NoBrush)
    if isinstance(paint, Color):
        return QBrush(qcolor(paint))
    g: Gradient = paint
    x, y, w, h = bbox.x(), bbox.y(), max(bbox.width(), 1e-6), max(bbox.height(), 1e-6)
    if g.kind == "radial":
        qg = QRadialGradient(QPointF(0, 0), 1.0)
        m = QTransform(g.r * w, 0, 0, g.r * h, x + g.x1 * w, y + g.y1 * h)
    else:
        qg = QLinearGradient(QPointF(x + g.x1 * w, y + g.y1 * h), QPointF(x + g.x2 * w, y + g.y2 * h))
        m = QTransform()
    for s in g.stops:
        qg.setColorAt(max(0.0, min(1.0, s.offset)), qcolor(s.color))
    brush = QBrush(qg)
    brush.setTransform(m * world if world is not None else m)
    return brush


def make_pen(item: Item, bbox: QRectF, world: QTransform | None = None) -> QPen:
    if item.stroke is None or item.stroke_width <= 0:
        return QPen(Qt.NoPen)
    pen = QPen(make_brush(item.stroke, bbox, world), item.stroke_width)
    pen.setCapStyle(CAPS.get(item.stroke_cap, Qt.FlatCap))
    pen.setJoinStyle(JOINS.get(item.stroke_join, Qt.MiterJoin))
    pen.setMiterLimit(4.0)
    if item.dash:
        w = max(item.stroke_width, 1e-6)
        dashes = [d / w for d in item.dash]
        if len(dashes) % 2:
            dashes *= 2
        pen.setDashPattern(dashes)
    return pen


def paint_preview_color(paint) -> QColor:
    if paint is None:
        return QColor(0, 0, 0, 0)
    if isinstance(paint, Gradient):
        return qcolor(paint.first_color())
    return qcolor(paint)
