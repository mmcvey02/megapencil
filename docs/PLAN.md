# MegaPencil – build plan

MegaPencil is an original vector graphics editor (Python 3.11+, PySide6).

## Data model (`megapencil.model`, pure Python, no Qt imports)

```
Document(width, height, guides)            # artboard size in px, guides = (("h"|"v", pos), ...)
 └─ children: [Layer]                      # bottom → top
     Layer(name, visible, locked, opacity)
      └─ children: [Item]                  # bottom → top
          Item (common): id, name, transform, fill, stroke, stroke_width,
                         stroke_cap, stroke_join, dash, opacity, visible, locked, parent
          ├─ RectItem(x, y, w, h, rx)
          ├─ EllipseItem(cx, cy, rx, ry)
          ├─ LineItem(x1, y1, x2, y2)
          ├─ PathItem(path: PathData)
          ├─ TextItem(x, y, text, font_family, font_size, bold, italic)
          └─ GroupItem(children: [Item])
```

* `Transform` – immutable 2×3 affine matrix (SVG `matrix(a b c d e f)` order).
* `PathData` → `SubPath(anchors, closed)` → `Anchor(x, y, hin, hout, smooth)`; handles are absolute
  points or `None`.  Path values are treated as immutable: edits build a new `PathData`.
* Paint = `None` | `Color(r, g, b, a)` | `Gradient(kind, stops, geometry in bounding-box units)`.
* Every item can produce `local_path()`; rendering, hit-testing, bounds, boolean ops and export all
  go through that single representation.  Strokes are never scaled by transforms
  (`vector-effect="non-scaling-stroke"` in SVG).

## Edits (`megapencil.commands`)

All edits are `QUndoCommand`s on a per-document `QUndoStack`.  Two generic commands cover everything:

* `PropertyCommand` – sets attributes on model objects (stores old/new values).
* `StructureCommand` – replaces the `children` list of containers (add, delete, reorder, group,
  layers).

The model notifies listeners (`Document.notify(kind, objs)`); the Qt scene re-syncs from that.

## Files

```
src/megapencil/
  __main__.py, app.py          entry point, QApplication, theme
  model/geometry.py            Transform, Bézier math
  model/path.py                Anchor/SubPath/PathData, SVG path parsing, shape→path
  model/paint.py               Color, Gradient
  model/items.py               items, Layer, Document
  model/ops.py                 align, distribute, group, arrange (pure functions)
  model/boolean.py             boolean path operations (pyclipper)
  model/svgio.py               SVG reader / writer (native format)
  commands.py                  undo commands
  ui/qtbridge.py               model ↔ Qt conversions, text outlines
  ui/scene.py, view.py, rulers.py, docwidget.py   canvas
  ui/tools/*.py                selection, direct selection, pen, shapes, text, hand, zoom
  ui/panels/*.py               Properties, Layers, Color, Stroke, Align
  ui/toolbox.py, controlbar.py, mainwindow.py, dialogs.py, theme.py, icons.py
  ui/state.py, settings.py, export.py, autosave.py
  resources/megapencil.svg     app icon
tests/                         pytest: model, path math, SVG round-trip, commands, GUI smoke
packaging/                     megapencil.desktop, build_deb.sh
```

## Milestones

1. Shell, artboard, zoom, pan  2. Shape tools  3. Selection tool  4. Pen / direct selection
5. Layers, arrange  6. Group, align, duplicate, clipboard  7. Undo/redo everywhere  8. Text
9. SVG I/O, PNG/PDF export, autosave  10. Booleans, gradients  11. Preferences, recents, shortcuts
12. Packaging
