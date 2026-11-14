"""Boolean path operations using pyclipper (Clipper polygon clipping).

Limits: curves are flattened to polylines (tolerance 0.05 px) before clipping,
so results are polygons with corner anchors; open paths are treated as closed.
"""
from __future__ import annotations

import pyclipper

from .path import PathData

SCALE = 1024.0
OPS = ("union", "subtract", "intersect", "exclude")


def _polys(path: PathData, tol: float):
    out = []
    for pts, _closed in path.flatten(tol):
        if len(pts) >= 3:
            out.append([(int(round(x * SCALE)), int(round(y * SCALE))) for x, y in pts])
    return out


def _clip(subject, clip, op):
    if not subject:
        return [] if op != pyclipper.CT_UNION and op != pyclipper.CT_XOR else clip
    pc = pyclipper.Pyclipper()
    pc.AddPaths(subject, pyclipper.PT_SUBJECT, True)
    if clip:
        pc.AddPaths(clip, pyclipper.PT_CLIP, True)
    return pc.Execute(op, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def boolean_op(paths: list[PathData], op: str, tol: float = 0.05) -> PathData:
    """Combine paths (document coordinates, bottom → top order).

    union: all shapes merged; intersect: area common to all; exclude: xor;
    subtract: the bottom shape minus every shape above it.
    """
    if op not in OPS:
        raise ValueError(op)
    polys = [_polys(p, tol) for p in paths]
    ct = {"union": pyclipper.CT_UNION, "subtract": pyclipper.CT_DIFFERENCE,
          "intersect": pyclipper.CT_INTERSECTION, "exclude": pyclipper.CT_XOR}[op]
    if not polys:
        return PathData()
    result = _clip(polys[0], [], pyclipper.CT_UNION)  # normalise self-intersections
    if op == "subtract":
        clip = [p for ps in polys[1:] for p in ps]
        if clip:
            result = _clip(result, _clip(clip, [], pyclipper.CT_UNION), ct)
    else:
        for ps in polys[1:]:
            result = _clip(result, ps, ct)
    out = PathData()
    for poly in result:
        if len(poly) >= 3:
            out.subpaths += PathData.from_polygon([(x / SCALE, y / SCALE) for x, y in poly]).subpaths
    return out
