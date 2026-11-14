"""Paint values: solid colours and gradients (immutable)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import NamedTuple


class Color(NamedTuple):
    r: int = 0
    g: int = 0
    b: int = 0
    a: float = 1.0

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def with_alpha(self, a: float) -> "Color":
        return Color(self.r, self.g, self.b, a)

    @staticmethod
    def parse(text: str | None) -> "Color | None":
        """Parse a CSS colour. Returns None for 'none' or unparseable input."""
        if not text:
            return None
        s = text.strip().lower()
        if s in ("none", "transparent"):
            return None
        if s in NAMED:
            s = NAMED[s]
        if s.startswith("#"):
            h = s[1:]
            if len(h) in (3, 4):
                h = "".join(ch * 2 for ch in h)
            if len(h) in (6, 8) and re.fullmatch(r"[0-9a-f]+", h):
                a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
                return Color(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
            return None
        m = re.fullmatch(r"rgba?\(([^)]*)\)", s)
        if m:
            parts = [p for p in re.split(r"[\s,/]+", m.group(1).strip()) if p]
            if len(parts) >= 3:
                try:
                    ch = [_channel(p) for p in parts[:3]]
                    a = float(parts[3].rstrip("%")) / (100 if parts[3].endswith("%") else 1) if len(parts) > 3 else 1.0
                    return Color(ch[0], ch[1], ch[2], max(0.0, min(1.0, a)))
                except ValueError:
                    return None
        return None


def _channel(p: str) -> int:
    v = float(p[:-1]) * 2.55 if p.endswith("%") else float(p)
    return max(0, min(255, int(round(v))))


NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "yellow": "#ffff00", "cyan": "#00ffff", "aqua": "#00ffff", "magenta": "#ff00ff", "fuchsia": "#ff00ff",
    "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0", "maroon": "#800000", "olive": "#808000",
    "lime": "#00ff00", "teal": "#008080", "navy": "#000080", "purple": "#800080", "orange": "#ffa500",
    "pink": "#ffc0cb", "brown": "#a52a2a", "gold": "#ffd700", "indigo": "#4b0082", "violet": "#ee82ee",
    "coral": "#ff7f50", "salmon": "#fa8072", "khaki": "#f0e68c", "crimson": "#dc143c", "tomato": "#ff6347",
    "turquoise": "#40e0d0", "skyblue": "#87ceeb", "steelblue": "#4682b4", "darkgray": "#a9a9a9",
    "darkgrey": "#a9a9a9", "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3", "dimgray": "#696969",
    "darkblue": "#00008b", "darkgreen": "#006400", "darkred": "#8b0000", "lightblue": "#add8e6",
    "lightgreen": "#90ee90", "beige": "#f5f5dc", "ivory": "#fffff0", "tan": "#d2b48c",
}

BLACK = Color(0, 0, 0)
WHITE = Color(255, 255, 255)


class GradientStop(NamedTuple):
    offset: float
    color: Color


@dataclass(frozen=True)
class Gradient:
    """Gradient in bounding-box units (0..1) of the object it paints.

    linear: from (x1, y1) to (x2, y2); radial: centre (x1, y1), radius ``r``.
    """

    kind: str = "linear"  # "linear" | "radial"
    stops: tuple[GradientStop, ...] = (GradientStop(0.0, WHITE), GradientStop(1.0, BLACK))
    x1: float = 0.0
    y1: float = 0.5
    x2: float = 1.0
    y2: float = 0.5
    r: float = 0.5

    @staticmethod
    def linear(stops, angle_deg: float = 0.0) -> "Gradient":
        r = math.radians(angle_deg)
        dx, dy = math.cos(r) / 2, math.sin(r) / 2
        return Gradient("linear", tuple(stops), 0.5 - dx, 0.5 - dy, 0.5 + dx, 0.5 + dy)

    @staticmethod
    def radial(stops) -> "Gradient":
        return Gradient("radial", tuple(stops), 0.5, 0.5, 1.0, 0.5, 0.5)

    def angle(self) -> float:
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))

    def first_color(self) -> Color:
        return self.stops[0].color if self.stops else BLACK


Paint = Color | Gradient | None
