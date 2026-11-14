"""Pure model operations.  They compute new values; commands apply them."""
from __future__ import annotations

from .geometry import Bounds, Transform, union_bounds
from .items import GroupItem, Item, Layer


def apply_world(item: Item, m: Transform) -> Transform:
    """New local transform of ``item`` after applying ``m`` in document space."""
    p = item.parent_world()
    if p.is_identity():
        return m.mul(item.transform)
    return p.inverted().mul(m).mul(p).mul(item.transform)


def selection_bounds(items) -> Bounds | None:
    return union_bounds(it.bounds() for it in items)


def top_level_only(items) -> list[Item]:
    """Drop items whose ancestor is also in the list."""
    ids = {id(i) for i in items}
    out = []
    for it in items:
        p = it.parent
        while isinstance(p, GroupItem) and id(p) not in ids:
            p = p.parent
        if not isinstance(p, GroupItem):
            out.append(it)
    return out


def doc_order(doc, items) -> list[Item]:
    """Sort items bottom → top in document order."""
    order = {id(it): i for i, it in enumerate(doc.all_items())}
    return sorted(items, key=lambda it: order.get(id(it), -1))


# ---------------------------------------------------------------------
# Align / distribute: return {item: (dx, dy)}
# ---------------------------------------------------------------------
ALIGN_MODES = ("left", "hcenter", "right", "top", "vcenter", "bottom")
DISTRIBUTE_MODES = ("hcenters", "vcenters", "hspace", "vspace")


def align(items, mode: str, ref: Bounds | None = None) -> dict[Item, tuple[float, float]]:
    boxes = {it: it.bounds() for it in items}
    boxes = {it: b for it, b in boxes.items() if b}
    ref = ref or union_bounds(boxes.values())
    out = {}
    if not ref:
        return out
    for it, b in boxes.items():
        dx = dy = 0.0
        if mode == "left":
            dx = ref[0] - b[0]
        elif mode == "right":
            dx = ref[2] - b[2]
        elif mode == "hcenter":
            dx = (ref[0] + ref[2]) / 2 - (b[0] + b[2]) / 2
        elif mode == "top":
            dy = ref[1] - b[1]
        elif mode == "bottom":
            dy = ref[3] - b[3]
        elif mode == "vcenter":
            dy = (ref[1] + ref[3]) / 2 - (b[1] + b[3]) / 2
        else:
            raise ValueError(mode)
        if dx or dy:
            out[it] = (dx, dy)
    return out


def distribute(items, mode: str) -> dict[Item, tuple[float, float]]:
    boxes = [(it, it.bounds()) for it in items]
    boxes = [(it, b) for it, b in boxes if b]
    if len(boxes) < 3:
        return {}
    ax = 0 if mode in ("hcenters", "hspace") else 1
    boxes.sort(key=lambda ib: (ib[1][ax] + ib[1][ax + 2]) / 2)
    out = {}
    if mode in ("hcenters", "vcenters"):
        centers = [(b[ax] + b[ax + 2]) / 2 for _, b in boxes]
        step = (centers[-1] - centers[0]) / (len(boxes) - 1)
        for i, (it, _) in enumerate(boxes):
            d = centers[0] + step * i - centers[i]
            if abs(d) > 1e-9:
                out[it] = (d, 0.0) if ax == 0 else (0.0, d)
    else:
        total = sum(b[ax + 2] - b[ax] for _, b in boxes)
        span = boxes[-1][1][ax + 2] - boxes[0][1][ax]
        gap = (span - total) / (len(boxes) - 1)
        pos = boxes[0][1][ax]
        for it, b in boxes:
            d = pos - b[ax]
            if abs(d) > 1e-9:
                out[it] = (d, 0.0) if ax == 0 else (0.0, d)
            pos += b[ax + 2] - b[ax] + gap
    return out


# ---------------------------------------------------------------------
# Structure: return [(container, new_children)]
# ---------------------------------------------------------------------
def remove_items(items) -> list[tuple[object, list]]:
    by_parent: dict[int, tuple[object, set]] = {}
    for it in items:
        by_parent.setdefault(id(it.parent), (it.parent, set()))[1].add(id(it))
    return [(par, [c for c in par.children if id(c) not in ids]) for par, ids in by_parent.values()]


def arrange(items, how: str) -> list[tuple[object, list]]:
    """how: front | back | forward | backward (within each parent)."""
    by_parent: dict[int, tuple[object, set]] = {}
    for it in items:
        by_parent.setdefault(id(it.parent), (it.parent, set()))[1].add(id(it))
    out = []
    for par, ids in by_parent.values():
        ch = list(par.children)
        sel = [c for c in ch if id(c) in ids]
        rest = [c for c in ch if id(c) not in ids]
        if how == "front":
            new = rest + sel
        elif how == "back":
            new = sel + rest
        elif how == "forward":
            new = list(ch)
            for i in range(len(new) - 2, -1, -1):
                if id(new[i]) in ids and id(new[i + 1]) not in ids:
                    new[i], new[i + 1] = new[i + 1], new[i]
        elif how == "backward":
            new = list(ch)
            for i in range(1, len(new)):
                if id(new[i]) in ids and id(new[i - 1]) not in ids:
                    new[i], new[i - 1] = new[i - 1], new[i]
        else:
            raise ValueError(how)
        if new != ch:
            out.append((par, new))
    return out


def group(doc, items) -> tuple[GroupItem, list[tuple[object, list]]] | None:
    """Group items into the parent of the top-most one."""
    items = doc_order(doc, top_level_only(items))
    if not items:
        return None
    top = items[-1]
    parent = top.parent
    ids = {id(i) for i in items}
    g = GroupItem()
    changes: dict[int, tuple[object, list]] = {}
    for it in items:
        if id(it.parent) not in changes:
            changes[id(it.parent)] = (it.parent, list(it.parent.children))
    new_parent_children = []
    for c in parent.children:
        if c is top:
            new_parent_children.append(g)
        elif id(c) not in ids:
            new_parent_children.append(c)
    changes[id(parent)] = (parent, new_parent_children)
    for pid, (par, ch) in list(changes.items()):
        if par is not parent:
            changes[pid] = (par, [c for c in ch if id(c) not in ids])
    # Children keep their document-space placement.
    pw = parent.parent_world().mul(parent.transform) if isinstance(parent, GroupItem) else Transform()
    inv = pw.inverted()
    g_children = []
    transforms = {}
    for it in items:
        transforms[it] = inv.mul(it.world_transform())
        g_children.append(it)
    return g, list(changes.values()) + [(g, g_children)], transforms  # type: ignore[return-value]


def ungroup(g: GroupItem):
    """Return (structure changes, {child: (transform, opacity)})."""
    parent = g.parent
    new = []
    for c in parent.children:
        if c is g:
            new.extend(g.children)
        else:
            new.append(c)
    props = {c: (g.transform.mul(c.transform), c.opacity * g.opacity) for c in g.children}
    return [(parent, new), (g, [])], props


def editable_layer(layer: Layer | None) -> bool:
    return layer is not None and layer.editable()
