"""Path data: anchors with Bézier handles, SVG path parsing/serialising.

Path values are treated as immutable by the rest of the program: editing
functions return a new :class:`PathData`.
"""
from __future__ import annotations

import math
import re

from .geometry import (Bounds, Point, Transform, cubic_bounds, cubic_split, flatten_cubic, fmt,
                       nearest_on_cubic, nearest_on_line, union_bounds)

KAPPA = 0.5522847498307936  # circle approximation constant


class Anchor:
    __slots__ = ("x", "y", "hin", "hout", "smooth")

    def __init__(self, x: float, y: float, hin: Point | None = None, hout: Point | None = None,
                 smooth: bool = False):
        self.x = float(x)
        self.y = float(y)
        self.hin = hin
        self.hout = hout
        self.smooth = smooth

    @property
    def p(self) -> Point:
        return (self.x, self.y)

    def copy(self) -> "Anchor":
        return Anchor(self.x, self.y, self.hin, self.hout, self.smooth)

    def transformed(self, t: Transform) -> "Anchor":
        x, y = t.map(self.x, self.y)
        return Anchor(x, y, t.map(*self.hin) if self.hin else None,
                      t.map(*self.hout) if self.hout else None, self.smooth)

    def __eq__(self, o) -> bool:
        return (isinstance(o, Anchor) and _close(self.p, o.p) and _opt_close(self.hin, o.hin)
                and _opt_close(self.hout, o.hout))

    def __repr__(self) -> str:
        return f"Anchor({self.x:g}, {self.y:g}, hin={self.hin}, hout={self.hout})"


def _close(p: Point, q: Point, eps: float = 1e-6) -> bool:
    return abs(p[0] - q[0]) <= eps and abs(p[1] - q[1]) <= eps


def _opt_close(p, q) -> bool:
    if p is None or q is None:
        return p is None and q is None
    return _close(p, q, 1e-6)


class SubPath:
    __slots__ = ("anchors", "closed")

    def __init__(self, anchors: list[Anchor] | None = None, closed: bool = False):
        self.anchors = anchors or []
        self.closed = closed

    def copy(self) -> "SubPath":
        return SubPath([a.copy() for a in self.anchors], self.closed)

    def segment_count(self) -> int:
        n = len(self.anchors)
        if n < 2:
            return 0
        return n if self.closed else n - 1

    def segment(self, i: int) -> tuple[Anchor, Anchor]:
        n = len(self.anchors)
        return self.anchors[i], self.anchors[(i + 1) % n]

    def segment_points(self, i: int):
        """Return (p0, c1, c2, p3, is_curve) for segment ``i``."""
        a, b = self.segment(i)
        curve = a.hout is not None or b.hin is not None
        return a.p, a.hout or a.p, b.hin or b.p, b.p, curve

    def reversed(self) -> "SubPath":
        return SubPath([Anchor(a.x, a.y, a.hout, a.hin, a.smooth) for a in reversed(self.anchors)], self.closed)

    def __eq__(self, o) -> bool:
        return isinstance(o, SubPath) and self.closed == o.closed and self.anchors == o.anchors


class PathData:
    __slots__ = ("subpaths",)

    def __init__(self, subpaths: list[SubPath] | None = None):
        self.subpaths = subpaths or []

    def copy(self) -> "PathData":
        return PathData([s.copy() for s in self.subpaths])

    def __eq__(self, o) -> bool:
        return isinstance(o, PathData) and self.subpaths == o.subpaths

    def is_empty(self) -> bool:
        return not any(s.anchors for s in self.subpaths)

    def anchor_count(self) -> int:
        return sum(len(s.anchors) for s in self.subpaths)

    def transformed(self, t: Transform) -> "PathData":
        return PathData([SubPath([a.transformed(t) for a in s.anchors], s.closed) for s in self.subpaths])

    # -- geometry -----------------------------------------------------
    def bounds(self) -> Bounds | None:
        out = []
        for s in self.subpaths:
            if len(s.anchors) == 1:
                x, y = s.anchors[0].p
                out.append((x, y, x, y))
            for i in range(s.segment_count()):
                p0, c1, c2, p3, curve = s.segment_points(i)
                if curve:
                    out.append(cubic_bounds(p0, c1, c2, p3))
                else:
                    out.append((min(p0[0], p3[0]), min(p0[1], p3[1]), max(p0[0], p3[0]), max(p0[1], p3[1])))
        return union_bounds(out)

    def flatten(self, tol: float = 0.1) -> list[tuple[list[Point], bool]]:
        out = []
        for s in self.subpaths:
            if not s.anchors:
                continue
            pts = [s.anchors[0].p]
            for i in range(s.segment_count()):
                p0, c1, c2, p3, curve = s.segment_points(i)
                if curve:
                    pts += flatten_cubic(p0, c1, c2, p3, tol)
                else:
                    pts.append(p3)
            if s.closed and len(pts) > 1 and _close(pts[0], pts[-1]):
                pts.pop()
            out.append((pts, s.closed))
        return out

    def nearest_segment(self, x: float, y: float):
        """Return (subpath index, segment index, t, distance) or None."""
        best = None
        for si, s in enumerate(self.subpaths):
            for i in range(s.segment_count()):
                p0, c1, c2, p3, curve = s.segment_points(i)
                t, d = nearest_on_cubic(p0, c1, c2, p3, x, y) if curve else nearest_on_line(p0, p3, x, y)
                if best is None or d < best[3]:
                    best = (si, i, t, d)
        return best

    # -- editing (return new PathData) --------------------------------
    def insert_anchor(self, si: int, seg: int, t: float) -> "PathData":
        new = self.copy()
        s = new.subpaths[si]
        a, b = s.segment(seg)
        p0, c1, c2, p3, curve = s.segment_points(seg)
        if curve:
            left, right = cubic_split(p0, c1, c2, p3, t)
            a.hout = left[1]
            b.hin = right[2]
            mid = Anchor(left[3][0], left[3][1], left[2], right[1], smooth=True)
        else:
            mid = Anchor(p0[0] + (p3[0] - p0[0]) * t, p0[1] + (p3[1] - p0[1]) * t)
        s.anchors.insert(seg + 1, mid)
        return new

    def delete_anchor(self, si: int, ai: int) -> "PathData":
        new = self.copy()
        s = new.subpaths[si]
        del s.anchors[ai]
        if len(s.anchors) < 2:
            del new.subpaths[si]
        elif not s.closed:
            s.anchors[0].hin = None
            s.anchors[-1].hout = None
        return new

    def with_anchor(self, si: int, ai: int, anchor: Anchor) -> "PathData":
        new = self.copy()
        new.subpaths[si].anchors[ai] = anchor
        return new

    # -- SVG ----------------------------------------------------------
    def to_svg(self) -> str:
        parts: list[str] = []
        for s in self.subpaths:
            if not s.anchors:
                continue
            a0 = s.anchors[0]
            parts.append(f"M{fmt(a0.x)} {fmt(a0.y)}")
            for i in range(s.segment_count()):
                p0, c1, c2, p3, curve = s.segment_points(i)
                if curve:
                    parts.append("C%s %s %s %s %s %s" % tuple(fmt(v) for v in (*c1, *c2, *p3)))
                elif not (s.closed and i == len(s.anchors) - 1):
                    parts.append(f"L{fmt(p3[0])} {fmt(p3[1])}")
            if s.closed:
                parts.append("Z")
        return " ".join(parts)

    @staticmethod
    def from_svg(d: str) -> "PathData":
        return _parse_svg_path(d)

    @staticmethod
    def from_polygon(points: list[Point], closed: bool = True) -> "PathData":
        return PathData([SubPath([Anchor(x, y) for x, y in points], closed)])


# ---------------------------------------------------------------------
# Shape constructors
# ---------------------------------------------------------------------
def rect_path(x: float, y: float, w: float, h: float, rx: float = 0.0) -> PathData:
    rx = max(0.0, min(rx, abs(w) / 2, abs(h) / 2))
    x0, y0, x1, y1 = x, y, x + w, y + h
    if rx <= 0:
        return PathData.from_polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    k = rx * (1 - KAPPA)
    a = [
        Anchor(x0 + rx, y0, hin=(x0 + k, y0)),
        Anchor(x1 - rx, y0, hout=(x1 - k, y0)),
        Anchor(x1, y0 + rx, hin=(x1, y0 + k)),
        Anchor(x1, y1 - rx, hout=(x1, y1 - k)),
        Anchor(x1 - rx, y1, hin=(x1 - k, y1)),
        Anchor(x0 + rx, y1, hout=(x0 + k, y1)),
        Anchor(x0, y1 - rx, hin=(x0, y1 - k)),
        Anchor(x0, y0 + rx, hout=(x0, y0 + k)),
    ]
    return PathData([SubPath(a, True)])


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> PathData:
    kx, ky = rx * KAPPA, ry * KAPPA
    a = [
        Anchor(cx + rx, cy, (cx + rx, cy - ky), (cx + rx, cy + ky), True),
        Anchor(cx, cy + ry, (cx + kx, cy + ry), (cx - kx, cy + ry), True),
        Anchor(cx - rx, cy, (cx - rx, cy + ky), (cx - rx, cy - ky), True),
        Anchor(cx, cy - ry, (cx - kx, cy - ry), (cx + kx, cy - ry), True),
    ]
    return PathData([SubPath(a, True)])


def line_path(x1: float, y1: float, x2: float, y2: float) -> PathData:
    return PathData([SubPath([Anchor(x1, y1), Anchor(x2, y2)], False)])


# ---------------------------------------------------------------------
# SVG path parser
# ---------------------------------------------------------------------
_NUM_RE = re.compile(r"[\s,]*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_CMD_RE = re.compile(r"[\s,]*([MmLlHhVvCcSsQqTtAaZz])")
_FLAG_RE = re.compile(r"[\s,]*([01])")


def _is_smooth(a: Anchor) -> bool:
    if a.hin is None or a.hout is None:
        return False
    v1 = (a.x - a.hin[0], a.y - a.hin[1])
    v2 = (a.hout[0] - a.x, a.hout[1] - a.y)
    l1, l2 = math.hypot(*v1), math.hypot(*v2)
    if l1 < 1e-9 or l2 < 1e-9:
        return False
    return abs(v1[0] * v2[1] - v1[1] * v2[0]) / (l1 * l2) < 1e-3 and (v1[0] * v2[0] + v1[1] * v2[1]) > 0


def _parse_svg_path(d: str) -> PathData:
    pos = 0
    n = len(d)
    subpaths: list[SubPath] = []
    cur: SubPath | None = None
    cx = cy = sx = sy = 0.0
    last_c2: Point | None = None  # for S
    last_q: Point | None = None  # for T

    def num() -> float:
        nonlocal pos
        m = _NUM_RE.match(d, pos)
        if not m:
            raise ValueError("bad path data")
        pos = m.end()
        return float(m.group(1))

    def flag() -> int:
        nonlocal pos
        m = _FLAG_RE.match(d, pos)
        if not m:
            raise ValueError("bad arc flag")
        pos = m.end()
        return int(m.group(1))

    def has_num() -> bool:
        return _NUM_RE.match(d, pos) is not None

    def ensure() -> SubPath:
        nonlocal cur
        if cur is None:
            cur = SubPath([Anchor(cx, cy)])
            subpaths.append(cur)
        return cur

    def line_to(x: float, y: float) -> None:
        nonlocal cx, cy
        ensure().anchors.append(Anchor(x, y))
        cx, cy = x, y

    def curve_to(c1: Point, c2: Point, p: Point) -> None:
        nonlocal cx, cy
        s = ensure()
        last = s.anchors[-1]
        last.hout = None if _close(c1, last.p, 1e-9) else c1
        s.anchors.append(Anchor(p[0], p[1], hin=None if _close(c2, p, 1e-9) else c2))
        cx, cy = p

    try:
        while pos < n:
            m = _CMD_RE.match(d, pos)
            if not m:
                break
            cmd = m.group(1)
            pos = m.end()
            rel = cmd.islower()
            c = cmd.upper()
            if c == "Z":
                if cur is not None:
                    cur.closed = True
                    a = cur.anchors
                    if len(a) > 1 and _close(a[0].p, a[-1].p):
                        a[0].hin = a[-1].hin
                        a.pop()
                cx, cy = sx, sy
                cur = None
                last_c2 = last_q = None
                continue
            first = True
            while first or has_num():
                ox, oy = (cx, cy) if rel else (0.0, 0.0)
                if c == "M":
                    x, y = num() + ox, num() + oy
                    if first:
                        cur = SubPath([Anchor(x, y)])
                        subpaths.append(cur)
                        cx, cy = sx, sy = x, y
                    else:
                        line_to(x, y)
                    last_c2 = last_q = None
                elif c == "L":
                    line_to(num() + ox, num() + oy)
                    last_c2 = last_q = None
                elif c == "H":
                    line_to(num() + ox, cy)
                    last_c2 = last_q = None
                elif c == "V":
                    line_to(cx, num() + oy)
                    last_c2 = last_q = None
                elif c in "CS":
                    if c == "C":
                        c1 = (num() + ox, num() + oy)
                    else:
                        c1 = (2 * cx - last_c2[0], 2 * cy - last_c2[1]) if last_c2 else (cx, cy)
                    c2 = (num() + ox, num() + oy)
                    p = (num() + ox, num() + oy)
                    curve_to(c1, c2, p)
                    last_c2, last_q = c2, None
                elif c in "QT":
                    if c == "Q":
                        q = (num() + ox, num() + oy)
                    else:
                        q = (2 * cx - last_q[0], 2 * cy - last_q[1]) if last_q else (cx, cy)
                    p = (num() + ox, num() + oy)
                    p0 = (cx, cy)
                    c1 = (p0[0] + 2 / 3 * (q[0] - p0[0]), p0[1] + 2 / 3 * (q[1] - p0[1]))
                    c2 = (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1]))
                    curve_to(c1, c2, p)
                    last_q, last_c2 = q, None
                elif c == "A":
                    rx, ry, rot = num(), num(), num()
                    large, sweep = flag(), flag()
                    x, y = num() + ox, num() + oy
                    for c1, c2, p in arc_to_cubics(cx, cy, rx, ry, rot, large, sweep, x, y):
                        curve_to(c1, c2, p)
                    if (cx, cy) != (x, y):
                        line_to(x, y) if not cur or not _close(cur.anchors[-1].p, (x, y)) else None
                        cx, cy = x, y
                    last_c2 = last_q = None
                first = False
    except ValueError:
        pass  # keep what was parsed so far, as SVG renderers do
    out = PathData([s for s in subpaths if s.anchors])
    for s in out.subpaths:
        for a in s.anchors:
            a.smooth = _is_smooth(a)
    return out


def arc_to_cubics(x1, y1, rx, ry, phi_deg, large, sweep, x2, y2):
    """Convert an SVG elliptical arc to a list of cubic segments (c1, c2, end)."""
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-12 or ry < 1e-12:
        return [((x1, y1), (x2, y2), (x2, y2))]
    phi = math.radians(phi_deg)
    cs, sn = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cs * dx + sn * dy, -sn * dx + cs * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cs * cxp - sn * cyp + (x1 + x2) / 2
    cy = sn * cxp + cs * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    th1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    segs = max(1, int(math.ceil(abs(dth) / (math.pi / 2) - 1e-9)))
    delta = dth / segs
    t = 4 / 3 * math.tan(delta / 4)
    out = []

    def pt(th):
        c, s = math.cos(th), math.sin(th)
        return (cx + rx * c * cs - ry * s * sn, cy + rx * c * sn + ry * s * cs)

    def deriv(th):
        c, s = math.cos(th), math.sin(th)
        return (-rx * s * cs - ry * c * sn, -rx * s * sn + ry * c * cs)

    th = th1
    for _ in range(segs):
        p0, p3 = pt(th), pt(th + delta)
        d0, d3 = deriv(th), deriv(th + delta)
        out.append(((p0[0] + t * d0[0], p0[1] + t * d0[1]), (p3[0] - t * d3[0], p3[1] - t * d3[1]), p3))
        th += delta
    out[-1] = (out[-1][0], out[-1][1], (x2, y2))
    return out
