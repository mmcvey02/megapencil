"""SVG reader / writer.  SVG is MegaPencil's native format.

Layers are ``<g inkscape:groupmode="layer">`` so files open with layers in
Inkscape too.  Unsupported on import: images, <use>, clipping/masks, patterns,
CSS stylesheets, gradientTransform.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .geometry import IDENTITY, Transform, fmt
from .items import Document, EllipseItem, GroupItem, Item, Layer, LineItem, PathItem, RectItem, TextItem
from .paint import BLACK, Color, Gradient, GradientStop
from .path import PathData

SVG = "http://www.w3.org/2000/svg"
INK = "http://www.inkscape.org/namespaces/inkscape"
SODI = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
XLINK = "http://www.w3.org/1999/xlink"
MP = "https://megapencil.app/ns"
XML = "http://www.w3.org/XML/1998/namespace"

for _p, _u in (("", SVG), ("inkscape", INK), ("sodipodi", SODI), ("xlink", XLINK), ("mp", MP)):
    ET.register_namespace(_p, _u)


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


# =====================================================================
# Writing
# =====================================================================
class _Writer:
    def __init__(self):
        self.defs: list[ET.Element] = []
        self.grad_ids: dict[Gradient, str] = {}

    def paint(self, el: ET.Element, attr: str, paint) -> None:
        if paint is None:
            el.set(attr, "none")
        elif isinstance(paint, Color):
            el.set(attr, paint.to_hex())
            if paint.a < 1:
                el.set(attr + "-opacity", fmt(paint.a))
        else:
            el.set(attr, f"url(#{self.gradient(paint)})")

    def gradient(self, g: Gradient) -> str:
        if g in self.grad_ids:
            return self.grad_ids[g]
        gid = f"gradient{len(self.grad_ids) + 1}"
        self.grad_ids[g] = gid
        if g.kind == "radial":
            el = ET.Element(_q(SVG, "radialGradient"), {"id": gid, "cx": fmt(g.x1), "cy": fmt(g.y1), "r": fmt(g.r)})
        else:
            el = ET.Element(_q(SVG, "linearGradient"), {"id": gid, "x1": fmt(g.x1), "y1": fmt(g.y1),
                                                        "x2": fmt(g.x2), "y2": fmt(g.y2)})
        for s in g.stops:
            st = ET.SubElement(el, _q(SVG, "stop"), {"offset": fmt(s.offset), "stop-color": s.color.to_hex()})
            if s.color.a < 1:
                st.set("stop-opacity", fmt(s.color.a))
        self.defs.append(el)
        return gid

    def common(self, el: ET.Element, it: Item) -> None:
        el.set("id", it.id)
        if it.name:
            el.set(_q(INK, "label"), it.name)
        if not it.transform.is_identity():
            el.set("transform", it.transform.to_svg())
        if it.opacity < 1:
            el.set("opacity", fmt(it.opacity))
        if not it.visible:
            el.set("display", "none")
        if it.locked:
            el.set(_q(SODI, "insensitive"), "true")

    def style(self, el: ET.Element, it: Item) -> None:
        self.paint(el, "fill", it.fill)
        self.paint(el, "stroke", it.stroke)
        if it.stroke is not None:
            el.set("stroke-width", fmt(it.stroke_width))
            if it.stroke_cap != "butt":
                el.set("stroke-linecap", it.stroke_cap)
            if it.stroke_join != "miter":
                el.set("stroke-linejoin", it.stroke_join)
            if it.dash:
                el.set("stroke-dasharray", " ".join(fmt(v) for v in it.dash))
            el.set("vector-effect", "non-scaling-stroke")

    def item(self, parent: ET.Element, it: Item) -> None:
        if isinstance(it, GroupItem):
            el = ET.SubElement(parent, _q(SVG, "g"))
            self.common(el, it)
            for c in it.children:
                self.item(el, c)
            return
        if isinstance(it, RectItem):
            el = ET.SubElement(parent, _q(SVG, "rect"), {"x": fmt(it.x), "y": fmt(it.y), "width": fmt(it.w),
                                                         "height": fmt(it.h)})
            if it.rx > 0:
                el.set("rx", fmt(it.rx))
                el.set("ry", fmt(it.rx))
        elif isinstance(it, EllipseItem):
            el = ET.SubElement(parent, _q(SVG, "ellipse"), {"cx": fmt(it.cx), "cy": fmt(it.cy), "rx": fmt(it.rx),
                                                            "ry": fmt(it.ry)})
        elif isinstance(it, LineItem):
            el = ET.SubElement(parent, _q(SVG, "line"), {"x1": fmt(it.x1), "y1": fmt(it.y1), "x2": fmt(it.x2),
                                                         "y2": fmt(it.y2)})
        elif isinstance(it, TextItem):
            el = ET.SubElement(parent, _q(SVG, "text"), {"x": fmt(it.x), "y": fmt(it.y),
                                                         "font-family": it.font_family,
                                                         "font-size": fmt(it.font_size)})
            el.set(_q(XML, "space"), "preserve")
            if it.bold:
                el.set("font-weight", "bold")
            if it.italic:
                el.set("font-style", "italic")
            lines = it.text.split("\n")
            if len(lines) == 1:
                el.text = it.text
            else:
                for i, line in enumerate(lines):
                    ts = ET.SubElement(el, _q(SVG, "tspan"), {"x": fmt(it.x), "dy": "0" if i == 0 else "1.2em"})
                    ts.set(_q(MP, "line"), "1")
                    ts.text = line
        else:
            el = ET.SubElement(parent, _q(SVG, "path"), {"d": it.local_path().to_svg()})
        self.common(el, it)
        self.style(el, it)


def to_element(doc: Document) -> ET.Element:
    w = _Writer()
    root = ET.Element(_q(SVG, "svg"), {
        "width": fmt(doc.width), "height": fmt(doc.height),
        "viewBox": f"0 0 {fmt(doc.width)} {fmt(doc.height)}", "version": "1.1",
    })
    root.set(_q(MP, "version"), "1")
    if doc.guides:
        root.set(_q(MP, "guides"), ";".join(f"{o}:{fmt(p)}" for o, p in doc.guides))
    defs = ET.SubElement(root, _q(SVG, "defs"))
    for layer in doc.children:
        g = ET.SubElement(root, _q(SVG, "g"), {"id": layer.id})
        g.set(_q(INK, "groupmode"), "layer")
        g.set(_q(INK, "label"), layer.name)
        if not layer.visible:
            g.set("style", "display:none")
        if layer.locked:
            g.set(_q(SODI, "insensitive"), "true")
        if layer.opacity < 1:
            g.set("opacity", fmt(layer.opacity))
        for it in layer.children:
            w.item(g, it)
    defs.extend(w.defs)
    if not w.defs:
        root.remove(defs)
    return root


def dumps(doc: Document) -> str:
    root = to_element(doc)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def save(doc: Document, path: str) -> None:
    data = dumps(doc)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)


# =====================================================================
# Reading
# =====================================================================
_UNITS = {"px": 1.0, "pt": 96 / 72, "pc": 16.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0, "": 1.0}
_INHERITED = ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "stroke-linecap",
              "stroke-linejoin", "stroke-dasharray", "font-family", "font-size", "font-weight", "font-style",
              "vector-effect")
_DEFAULT_STYLE = {"fill": "black", "stroke": "none", "stroke-width": "1"}


def parse_length(text: str | None, default: float = 0.0) -> float:
    if not text:
        return default
    m = re.fullmatch(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-z%]*)\s*", text)
    if not m or m.group(2) not in _UNITS:
        return default
    return float(m.group(1)) * _UNITS[m.group(2)]


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


class _Reader:
    def __init__(self, root: ET.Element):
        self.root = root
        self.grad_elems = {}
        for el in root.iter():
            if _local(el.tag) in ("linearGradient", "radialGradient") and el.get("id"):
                self.grad_elems[el.get("id")] = el
        self.skipped = 0

    # -- style --------------------------------------------------------
    def style_of(self, el: ET.Element, inherited: dict) -> dict:
        st = dict(inherited)
        own = {}
        for k in _INHERITED + ("opacity", "display", "visibility"):
            v = el.get(k)
            if v is not None:
                own[k] = v
        for decl in (el.get("style") or "").split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                own[k.strip()] = v.strip()
        for k, v in own.items():
            if v != "inherit":
                st[k] = v
        st["_own"] = own
        return st

    def gradient(self, gid: str, bbox) -> Gradient | None:
        el = self.grad_elems.get(gid)
        if el is None:
            return None
        chain, seen = [], set()
        cur = el
        while cur is not None and id(cur) not in seen:
            chain.append(cur)
            seen.add(id(cur))
            href = cur.get(_q(XLINK, "href")) or cur.get("href") or ""
            cur = self.grad_elems.get(href.lstrip("#"))

        def attr(name, default):
            for c in chain:
                if c.get(name) is not None:
                    return c.get(name)
            return default

        stops = []
        for c in chain:
            for s in c:
                if _local(s.tag) != "stop":
                    continue
                st = self.style_of(s, {})
                col = Color.parse(st.get("stop-color") or s.get("stop-color") or "black") or BLACK
                op = st.get("stop-opacity") or s.get("stop-opacity")
                if op:
                    col = col.with_alpha(_float(op, 1.0))
                off = s.get("offset", "0")
                o = float(off[:-1]) / 100 if off.endswith("%") else _float(off, 0.0)
                stops.append(GradientStop(max(0.0, min(1.0, o)), col))
            if stops:
                break
        if not stops:
            return None
        user = attr("gradientUnits", "objectBoundingBox") == "userSpaceOnUse"

        def coord(name, default, axis):
            raw = attr(name, default)
            v = float(raw[:-1]) / 100 if raw.endswith("%") else _float(raw, 0.0)
            if user and bbox:
                size = (bbox[2] - bbox[0]) if axis == 0 else (bbox[3] - bbox[1])
                if axis == 2:
                    size = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
                    return v / size if size else 0.5
                return (v - bbox[axis]) / size if size else 0.5
            return v

        if _local(el.tag) == "radialGradient":
            return Gradient("radial", tuple(stops), coord("cx", "50%", 0), coord("cy", "50%", 1), 1.0, 0.5,
                            coord("r", "50%", 2))
        return Gradient("linear", tuple(stops), coord("x1", "0%", 0), coord("y1", "0%", 1),
                        coord("x2", "100%", 0), coord("y2", "0%", 1))

    def paint(self, st: dict, key: str, bbox):
        raw = st.get(key, "none").strip()
        m = re.match(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)", raw)
        if m:
            return self.gradient(m.group(1), bbox)
        col = Color.parse(raw)
        if col is None:
            return None
        op = _float(st.get(key + "-opacity"), 1.0)
        return col.with_alpha(col.a * op) if op < 1 else col

    def apply_common(self, it: Item, el: ET.Element, st: dict, pre: Transform) -> None:
        if el.get("id"):
            it.id = el.get("id")
        it.name = el.get(_q(INK, "label")) or ""
        it.transform = pre.mul(Transform.parse(el.get("transform")))
        own = st["_own"]
        it.opacity = max(0.0, min(1.0, _float(own.get("opacity"), 1.0)))
        it.visible = own.get("display") != "none" and own.get("visibility") != "hidden"
        it.locked = el.get(_q(SODI, "insensitive")) == "true"

    def apply_style(self, it: Item, st: dict, world: Transform) -> None:
        bbox = it.local_path().bounds() if not isinstance(it, TextItem) else None
        it.fill = self.paint(st, "fill", bbox)
        it.stroke = self.paint(st, "stroke", bbox)
        sw = parse_length(st.get("stroke-width"), 1.0)
        scale = 1.0 if st.get("vector-effect") == "non-scaling-stroke" else world.mean_scale()
        it.stroke_width = sw * scale
        cap, join = st.get("stroke-linecap", "butt"), st.get("stroke-linejoin", "miter")
        it.stroke_cap = cap if cap in ("butt", "round", "square") else "butt"
        it.stroke_join = join if join in ("miter", "round", "bevel") else "miter"
        dash = st.get("stroke-dasharray", "none")
        if dash and dash != "none":
            try:
                vals = tuple(parse_length(v) * scale for v in re.split(r"[\s,]+", dash.strip()) if v)
                it.dash = vals if any(v > 0 for v in vals) else ()
            except ValueError:
                it.dash = ()

    # -- elements -----------------------------------------------------
    def children(self, el: ET.Element, st: dict, pre: Transform, world: Transform) -> list[Item]:
        out = []
        for child in el:
            it = self.element(child, st, pre, world)
            if it is not None:
                out.append(it)
        return out

    def element(self, el: ET.Element, inherited: dict, pre: Transform, world: Transform) -> Item | None:
        tag = _local(el.tag)
        if tag in ("defs", "metadata", "title", "desc", "namedview", "style", "linearGradient", "radialGradient",
                   "clipPath", "mask", "pattern", "symbol", "marker", "filter", ""):
            return None
        st = self.style_of(el, inherited)
        length = lambda name: parse_length(el.get(name))  # noqa: E731
        it: Item
        if tag == "g":
            it = GroupItem()
            self.apply_common(it, el, st, pre)
            it.children = self.children(el, st, IDENTITY, world.mul(it.transform))
            for c in it.children:
                c.parent = it
            return it if it.children else None
        if tag == "rect":
            rx = el.get("rx") or el.get("ry")
            it = RectItem(x=length("x"), y=length("y"), w=length("width"), h=length("height"), rx=parse_length(rx))
        elif tag in ("ellipse", "circle"):
            r = length("r")
            it = EllipseItem(cx=length("cx"), cy=length("cy"), rx=r if tag == "circle" else length("rx"),
                             ry=r if tag == "circle" else length("ry"))
        elif tag == "line":
            it = LineItem(x1=length("x1"), y1=length("y1"), x2=length("x2"), y2=length("y2"))
        elif tag in ("polyline", "polygon"):
            nums = [float(v) for v in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", el.get("points") or "")]
            pts = list(zip(nums[0::2], nums[1::2]))
            if len(pts) < 2:
                return None
            it = PathItem(path=PathData.from_polygon(pts, closed=(tag == "polygon")))
        elif tag == "path":
            path = PathData.from_svg(el.get("d") or "")
            if path.is_empty():
                return None
            it = PathItem(path=path)
        elif tag == "text":
            lines = []
            if el.text and el.text.strip():
                lines.append(el.text)
            for ts in el.iter():
                if ts is el:
                    continue
                if _local(ts.tag) == "tspan":
                    is_line = ts.get(_q(MP, "line")) or ts.get("x") is not None or ts.get("dy") is not None
                    if is_line or not lines:
                        lines.append(ts.text or "")
                    else:
                        lines[-1] += ts.text or ""
                if ts.tail and ts.tail.strip() and lines:
                    lines[-1] += ts.tail
            x, y = el.get("x"), el.get("y")
            first_ts = next((t for t in el if _local(t.tag) == "tspan"), None)
            if first_ts is not None:
                x = x or first_ts.get("x")
                y = y or first_ts.get("y")
            fam = (st.get("font-family") or "DejaVu Sans").split(",")[0].strip().strip("'\"")
            it = TextItem(x=parse_length((x or "0").split()[0]), y=parse_length((y or "0").split()[0]),
                          text="\n".join(lines), font_family=fam,
                          font_size=parse_length(st.get("font-size"), 16.0),
                          bold=st.get("font-weight", "normal") in ("bold", "bolder", "600", "700", "800", "900"),
                          italic=st.get("font-style", "normal") in ("italic", "oblique"))
            if not it.text:
                return None
        else:
            self.skipped += 1
            return None
        self.apply_common(it, el, st, pre)
        self.apply_style(it, st, world.mul(it.transform))
        return it


def _float(text, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def from_element(root: ET.Element) -> Document:
    if _local(root.tag) != "svg":
        raise ValueError("not an SVG document")
    vb = [float(v) for v in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", root.get("viewBox") or "")]
    has_vb = len(vb) == 4 and vb[2] > 0 and vb[3] > 0
    width = parse_length(root.get("width"), vb[2] if has_vb else 800.0) or (vb[2] if has_vb else 800.0)
    height = parse_length(root.get("height"), vb[3] if has_vb else 600.0) or (vb[3] if has_vb else 600.0)
    doc = Document(width, height)
    pre = IDENTITY
    if has_vb:
        pre = Transform.scaling(width / vb[2], height / vb[3]).mul(Transform.translation(-vb[0], -vb[1]))
    guides = []
    for part in (root.get(_q(MP, "guides")) or "").split(";"):
        if ":" in part:
            o, p = part.split(":", 1)
            if o in ("h", "v"):
                guides.append((o, _float(p, 0.0)))
    doc.guides = tuple(guides)

    r = _Reader(root)
    root_style = r.style_of(root, _DEFAULT_STYLE)
    loose: Layer | None = None
    for el in root:
        if _local(el.tag) == "g" and el.get(_q(INK, "groupmode")) == "layer":
            st = r.style_of(el, root_style)
            own = st["_own"]
            layer = Layer(el.get(_q(INK, "label")) or el.get("id") or "Layer")
            if el.get("id"):
                layer.id = el.get("id")
            layer.visible = own.get("display") != "none"
            layer.locked = el.get(_q(SODI, "insensitive")) == "true"
            layer.opacity = max(0.0, min(1.0, _float(own.get("opacity"), 1.0)))
            lt = pre.mul(Transform.parse(el.get("transform")))
            layer.children = r.children(el, st, lt, IDENTITY)
            for c in layer.children:
                c.parent = layer
            doc.add_layer(layer)
            loose = None
        else:
            it = r.element(el, root_style, pre, IDENTITY)
            if it is not None:
                if loose is None:
                    loose = doc.add_layer(Layer(f"Layer {len(doc.children) + 1}"))
                it.parent = loose
                loose.children.append(it)
    if not doc.children:
        doc.add_layer(Layer("Layer 1"))
    doc.import_skipped = r.skipped  # type: ignore[attr-defined]
    return doc


def loads(text: str) -> Document:
    return from_element(ET.fromstring(text))


def load(path: str) -> Document:
    return from_element(ET.parse(path).getroot())
