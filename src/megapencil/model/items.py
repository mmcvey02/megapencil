"""Document model: items, layers, document.  No Qt imports."""
from __future__ import annotations

import copy
import itertools
from typing import Callable, Iterator

from .geometry import IDENTITY, Bounds, Transform, union_bounds
from .paint import BLACK, Paint
from .path import PathData, ellipse_path, line_path, rect_path

_counter = itertools.count(1)

#: Optional hook installed by the UI layer: TextItem -> PathData of glyph outlines.
text_outliner: Callable[["TextItem"], PathData] | None = None

STYLE_ATTRS = ("fill", "stroke", "stroke_width", "stroke_cap", "stroke_join", "dash", "opacity")


def new_id(prefix: str) -> str:
    return f"{prefix}{next(_counter)}"


class Item:
    kind = "item"

    def __init__(self, **kw):
        self.id: str = new_id(self.kind)
        self.name: str = ""
        self.transform: Transform = IDENTITY
        self.fill: Paint = None
        self.stroke: Paint = None
        self.stroke_width: float = 1.0
        self.stroke_cap: str = "butt"  # butt | round | square
        self.stroke_join: str = "miter"  # miter | round | bevel
        self.dash: tuple[float, ...] = ()
        self.opacity: float = 1.0
        self.visible: bool = True
        self.locked: bool = False
        self.parent = None  # GroupItem | Layer | None
        for k, v in kw.items():
            if not hasattr(self, k):
                raise AttributeError(f"{type(self).__name__} has no attribute {k!r}")
            setattr(self, k, v)

    # -- tree ---------------------------------------------------------
    def layer(self) -> "Layer | None":
        p = self.parent
        while p is not None and not isinstance(p, Layer):
            p = p.parent
        return p

    def top_level(self) -> "Item":
        """The ancestor (or self) that is a direct child of a layer."""
        it = self
        while isinstance(it.parent, GroupItem):
            it = it.parent
        return it

    def leaves(self) -> Iterator["Item"]:
        yield self

    def display_name(self) -> str:
        return self.name or self.kind.capitalize()

    # -- geometry -----------------------------------------------------
    def parent_world(self) -> Transform:
        t = IDENTITY
        p = self.parent
        while isinstance(p, GroupItem):
            t = p.transform.mul(t)
            p = p.parent
        return t

    def world_transform(self) -> Transform:
        return self.parent_world().mul(self.transform)

    def local_path(self) -> PathData:
        return PathData()

    def world_path(self) -> PathData:
        return self.local_path().transformed(self.world_transform())

    def bounds(self) -> Bounds | None:
        """Geometric bounds in document coordinates (stroke not included)."""
        return self.world_path().bounds()

    def effective_opacity(self) -> float:
        o = self.opacity
        p = self.parent
        while isinstance(p, GroupItem):
            o *= p.opacity
            p = p.parent
        return o

    def effectively_visible(self) -> bool:
        p = self
        while p is not None and not isinstance(p, Document):
            if not p.visible:
                return False
            p = p.parent
        return True

    def effectively_locked(self) -> bool:
        p = self
        while p is not None and not isinstance(p, Document):
            if p.locked:
                return True
            p = p.parent
        return False

    # -- copying ------------------------------------------------------
    def clone(self) -> "Item":
        c = copy.copy(self)
        c.id = new_id(self.kind)
        c.parent = None
        return c

    def to_path_item(self) -> "PathItem":
        """A PathItem with the same geometry, style and identity."""
        p = PathItem(path=self.local_path())
        for a in STYLE_ATTRS + ("transform", "name", "visible", "locked", "id"):
            setattr(p, a, getattr(self, a))
        return p


class RectItem(Item):
    kind = "rect"

    def __init__(self, **kw):
        self.x = self.y = 0.0
        self.w = self.h = 0.0
        self.rx = 0.0
        super().__init__(**kw)

    def local_path(self) -> PathData:
        return rect_path(self.x, self.y, self.w, self.h, self.rx)


class EllipseItem(Item):
    kind = "ellipse"

    def __init__(self, **kw):
        self.cx = self.cy = 0.0
        self.rx = self.ry = 0.0
        super().__init__(**kw)

    def local_path(self) -> PathData:
        return ellipse_path(self.cx, self.cy, self.rx, self.ry)


class LineItem(Item):
    kind = "line"

    def __init__(self, **kw):
        self.x1 = self.y1 = self.x2 = self.y2 = 0.0
        super().__init__(**kw)

    def local_path(self) -> PathData:
        return line_path(self.x1, self.y1, self.x2, self.y2)


class PathItem(Item):
    kind = "path"

    def __init__(self, **kw):
        self.path = PathData()
        super().__init__(**kw)

    def local_path(self) -> PathData:
        return self.path


class TextItem(Item):
    kind = "text"

    def __init__(self, **kw):
        self.x = self.y = 0.0  # baseline origin of the first line
        self.text = ""
        self.font_family = "DejaVu Sans"
        self.font_size = 24.0
        self.bold = False
        self.italic = False
        super().__init__(**kw)
        if "fill" not in kw:
            self.fill = BLACK

    def local_path(self) -> PathData:
        if text_outliner is not None:
            return text_outliner(self)
        # Fallback without a font engine: one box per line.
        out = PathData()
        for i, line in enumerate(self.text.split("\n")):
            w = 0.6 * self.font_size * max(len(line), 1)
            y = self.y + i * self.font_size * 1.2
            out.subpaths += rect_path(self.x, y - 0.8 * self.font_size, w, self.font_size).subpaths
        return out


class GroupItem(Item):
    kind = "group"

    def __init__(self, **kw):
        self.children: list[Item] = []
        super().__init__(**kw)
        for c in self.children:
            c.parent = self

    def leaves(self) -> Iterator[Item]:
        for c in self.children:
            yield from c.leaves()

    def bounds(self) -> Bounds | None:
        return union_bounds(c.bounds() for c in self.children)

    def clone(self) -> "GroupItem":
        c = copy.copy(self)
        c.id = new_id(self.kind)
        c.parent = None
        c.children = [ch.clone() for ch in self.children]
        for ch in c.children:
            ch.parent = c
        return c


class Layer:
    kind = "layer"

    def __init__(self, name: str = "Layer", **kw):
        self.id = new_id("layer")
        self.name = name
        self.visible = True
        self.locked = False
        self.opacity = 1.0
        self.children: list[Item] = []
        self.parent: Document | None = None
        for k, v in kw.items():
            setattr(self, k, v)
        for c in self.children:
            c.parent = self

    def editable(self) -> bool:
        return self.visible and not self.locked


class Document:
    kind = "document"

    def __init__(self, width: float = 800.0, height: float = 600.0):
        self.width = float(width)
        self.height = float(height)
        self.children: list[Layer] = []  # bottom -> top
        self.guides: tuple[tuple[str, float], ...] = ()
        self.parent = None
        self.listeners: list[Callable[[str, list], None]] = []

    @property
    def layers(self) -> list[Layer]:
        return self.children

    @staticmethod
    def new(width: float = 800.0, height: float = 600.0) -> "Document":
        doc = Document(width, height)
        doc.add_layer(Layer("Layer 1"))
        return doc

    def add_layer(self, layer: Layer, index: int | None = None) -> Layer:
        layer.parent = self
        self.children.insert(len(self.children) if index is None else index, layer)
        return layer

    def add(self, item: Item, layer: Layer | None = None) -> Item:
        """Append directly (no undo); used when building documents."""
        layer = layer or self.children[-1]
        item.parent = layer
        layer.children.append(item)
        return item

    def top_items(self) -> Iterator[Item]:
        for layer in self.children:
            yield from layer.children

    def all_items(self) -> Iterator[Item]:
        def walk(items):
            for it in items:
                yield it
                if isinstance(it, GroupItem):
                    yield from walk(it.children)

        for layer in self.children:
            yield from walk(layer.children)

    def contains(self, obj) -> bool:
        p = obj
        while p is not None:
            par = p.parent
            if par is None:
                return p is self
            if p not in par.children:
                return False
            p = par
        return False

    def notify(self, kind: str, objs: list | None = None) -> None:
        """kind: 'props' (objs changed), 'structure' (tree changed), 'doc' (size/guides)."""
        for cb in list(self.listeners):
            cb(kind, objs or [])
