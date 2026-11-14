"""Affine transforms and Bézier math (pure Python)."""
from __future__ import annotations

import math
import re
from typing import NamedTuple

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]  # x0, y0, x1, y1


class Transform(NamedTuple):
    """2x3 affine matrix in SVG order: x' = a*x + c*y + e, y' = b*x + d*y + f."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    # -- constructors -------------------------------------------------
    @staticmethod
    def translation(dx: float, dy: float) -> "Transform":
        return Transform(1.0, 0.0, 0.0, 1.0, dx, dy)

    @staticmethod
    def scaling(sx: float, sy: float | None = None, cx: float = 0.0, cy: float = 0.0) -> "Transform":
        if sy is None:
            sy = sx
        return Transform(sx, 0.0, 0.0, sy, cx - sx * cx, cy - sy * cy)

    @staticmethod
    def rotation(degrees: float, cx: float = 0.0, cy: float = 0.0) -> "Transform":
        r = math.radians(degrees)
        cs, sn = math.cos(r), math.sin(r)
        return Transform(cs, sn, -sn, cs, cx - cs * cx + sn * cy, cy - sn * cx - cs * cy)

    # -- operations ---------------------------------------------------
    def mul(self, o: "Transform") -> "Transform":
        """Compose: the result applies ``o`` first, then ``self``."""
        return Transform(
            self.a * o.a + self.c * o.b,
            self.b * o.a + self.d * o.b,
            self.a * o.c + self.c * o.d,
            self.b * o.c + self.d * o.d,
            self.a * o.e + self.c * o.f + self.e,
            self.b * o.e + self.d * o.f + self.f,
        )

    def map(self, x: float, y: float) -> Point:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def det(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverted(self) -> "Transform":
        det = self.det()
        if abs(det) < 1e-12:
            return Transform()
        a, b, c, d = self.d / det, -self.b / det, -self.c / det, self.a / det
        return Transform(a, b, c, d, -(a * self.e + c * self.f), -(b * self.e + d * self.f))

    def is_identity(self, eps: float = 1e-9) -> bool:
        return all(abs(v - w) < eps for v, w in zip(self, (1, 0, 0, 1, 0, 0)))

    def mean_scale(self) -> float:
        return math.sqrt(abs(self.det()))

    # -- SVG ----------------------------------------------------------
    def to_svg(self) -> str:
        return "matrix(%s)" % " ".join(fmt(v, 6) for v in self)

    @staticmethod
    def parse(text: str | None) -> "Transform":
        t = Transform()
        if not text:
            return t
        for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
            v = [float(x) for x in re.findall(_NUM, args)]
            if name == "matrix" and len(v) == 6:
                m = Transform(*v)
            elif name == "translate" and v:
                m = Transform.translation(v[0], v[1] if len(v) > 1 else 0.0)
            elif name == "scale" and v:
                m = Transform.scaling(v[0], v[1] if len(v) > 1 else v[0])
            elif name == "rotate" and v:
                m = Transform.rotation(v[0], *(v[1:3] if len(v) >= 3 else (0.0, 0.0)))
            elif name == "skewX" and v:
                m = Transform(1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
            elif name == "skewY" and v:
                m = Transform(1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
            else:
                continue
            t = t.mul(m)
        return t


_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
IDENTITY = Transform()


def fmt(v: float, digits: int = 4) -> str:
    """Compact number formatting for SVG output."""
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------------
# Bounds helpers
# ---------------------------------------------------------------------
def union_bounds(bounds) -> Bounds | None:
    out = None
    for b in bounds:
        if b is None:
            continue
        if out is None:
            out = b
        else:
            out = (min(out[0], b[0]), min(out[1], b[1]), max(out[2], b[2]), max(out[3], b[3]))
    return out


def points_bounds(pts) -> Bounds | None:
    pts = list(pts)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------
# Cubic Bézier
# ---------------------------------------------------------------------
def lerp(p: Point, q: Point, t: float) -> Point:
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    mt = 1.0 - t
    a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def cubic_split(p0: Point, p1: Point, p2: Point, p3: Point, t: float):
    """De Casteljau split; returns two control polygons (4 points each)."""
    q0, q1, q2 = lerp(p0, p1, t), lerp(p1, p2, t), lerp(p2, p3, t)
    r0, r1 = lerp(q0, q1, t), lerp(q1, q2, t)
    s = lerp(r0, r1, t)
    return (p0, q0, r0, s), (s, r1, q2, p3)


def _axis_extrema(a: float, b: float, c: float, d: float) -> list[float]:
    """Parameters t in (0,1) where the derivative of a 1-D cubic vanishes."""
    qa = -a + 3 * b - 3 * c + d
    qb = 2 * (a - 2 * b + c)
    qc = b - a
    out = []
    if abs(qa) < 1e-12:
        if abs(qb) > 1e-12:
            out.append(-qc / qb)
    else:
        disc = qb * qb - 4 * qa * qc
        if disc >= 0:
            s = math.sqrt(disc)
            out += [(-qb + s) / (2 * qa), (-qb - s) / (2 * qa)]
    return [t for t in out if 0.0 < t < 1.0]


def cubic_bounds(p0: Point, p1: Point, p2: Point, p3: Point) -> Bounds:
    pts = [p0, p3]
    for axis in (0, 1):
        for t in _axis_extrema(p0[axis], p1[axis], p2[axis], p3[axis]):
            pts.append(cubic_point(p0, p1, p2, p3, t))
    return points_bounds(pts)  # type: ignore[return-value]


def flatten_cubic(p0: Point, p1: Point, p2: Point, p3: Point, tol: float = 0.1) -> list[Point]:
    """Points along the curve excluding p0, including p3."""
    ddx = max(abs(p0[0] - 2 * p1[0] + p2[0]), abs(p1[0] - 2 * p2[0] + p3[0]))
    ddy = max(abs(p0[1] - 2 * p1[1] + p2[1]), abs(p1[1] - 2 * p2[1] + p3[1]))
    n = int(math.ceil(math.sqrt(0.75 * math.hypot(ddx, ddy) / max(tol, 1e-6))))
    n = max(1, min(n, 256))
    return [cubic_point(p0, p1, p2, p3, i / n) for i in range(1, n)] + [p3]


def nearest_on_cubic(p0: Point, p1: Point, p2: Point, p3: Point, x: float, y: float) -> tuple[float, float]:
    """Return (t, distance) of the closest point on the curve to (x, y)."""

    def dist2(t: float) -> float:
        px, py = cubic_point(p0, p1, p2, p3, t)
        return (px - x) ** 2 + (py - y) ** 2

    n = 24
    best = min(range(n + 1), key=lambda i: dist2(i / n))
    lo, hi = max(0.0, (best - 1) / n), min(1.0, (best + 1) / n)
    for _ in range(24):  # ternary search
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if dist2(m1) < dist2(m2):
            hi = m2
        else:
            lo = m1
    t = (lo + hi) / 2
    return t, math.sqrt(dist2(t))


def nearest_on_line(p0: Point, p1: Point, x: float, y: float) -> tuple[float, float]:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = dx * dx + dy * dy
    t = 0.0 if ln < 1e-12 else max(0.0, min(1.0, ((x - p0[0]) * dx + (y - p0[1]) * dy) / ln))
    return t, math.hypot(p0[0] + dx * t - x, p0[1] + dy * t - y)


def constrain_angle(dx: float, dy: float, step_deg: float = 45.0) -> Point:
    """Snap the vector (dx, dy) to the nearest multiple of ``step_deg``."""
    ln = math.hypot(dx, dy)
    if ln == 0:
        return (0.0, 0.0)
    step = math.radians(step_deg)
    ang = round(math.atan2(dy, dx) / step) * step
    return (math.cos(ang) * ln, math.sin(ang) * ln)
