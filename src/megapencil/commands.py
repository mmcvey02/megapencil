"""Undo commands.  Every edit to a document goes through one of these."""
from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from .model import ops
from .model.geometry import Transform
from .model.items import Document, GroupItem, Item, Layer


class PropertyCommand(QUndoCommand):
    """Set attributes on model objects.

    ``changes`` is a list of ``(obj, attr, new)`` or ``(obj, attr, old, new)``.
    Commands with the same non-empty ``merge_key`` touching the same
    attributes merge (used for slider drags).
    """

    def __init__(self, doc: Document, changes, text: str = "Change", merge_key: str | None = None):
        super().__init__(text)
        self.doc = doc
        self.changes = []
        for ch in changes:
            if len(ch) == 3:
                obj, attr, new = ch
                old = getattr(obj, attr)
            else:
                obj, attr, old, new = ch
            self.changes.append((obj, attr, old, new))
        self.merge_key = merge_key

    def _apply(self, idx: int) -> None:
        objs = []
        for ch in self.changes:
            setattr(ch[0], ch[1], ch[idx])
            objs.append(ch[0])
        kind = "doc" if any(isinstance(o, Document) for o in objs) else "props"
        self.doc.notify(kind, objs)

    def redo(self) -> None:
        self._apply(3)

    def undo(self) -> None:
        self._apply(2)

    def id(self) -> int:
        return 1 if self.merge_key else -1

    def mergeWith(self, other) -> bool:
        if not isinstance(other, PropertyCommand) or other.merge_key != self.merge_key:
            return False
        mine = [(id(c[0]), c[1]) for c in self.changes]
        theirs = [(id(c[0]), c[1]) for c in other.changes]
        if mine != theirs:
            return False
        self.changes = [(a[0], a[1], a[2], b[3]) for a, b in zip(self.changes, other.changes)]
        return True


class StructureCommand(QUndoCommand):
    """Replace the ``children`` list of containers (document, layers, groups)."""

    def __init__(self, doc: Document, changes, text: str = "Edit"):
        super().__init__(text)
        self.doc = doc
        self.changes = [(c, list(c.children), list(new)) for c, new in changes]

    def _apply(self, idx: int) -> None:
        for ch in self.changes:
            ch[0].children = list(ch[idx])
        for ch in self.changes:
            for child in ch[idx]:
                child.parent = ch[0]
        self.doc.notify("structure", [c[0] for c in self.changes])

    def redo(self) -> None:
        self._apply(2)

    def undo(self) -> None:
        self._apply(1)


class Macro(QUndoCommand):
    """A composite command (children are applied in order)."""

    def __init__(self, text: str, commands=()):
        super().__init__(text)
        self.commands = list(commands)

    def redo(self) -> None:
        for c in self.commands:
            c.redo()

    def undo(self) -> None:
        for c in reversed(self.commands):
            c.undo()


# ---------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------
def add_items(doc, container, items, text="Add", index: int | None = None):
    ch = list(container.children)
    index = len(ch) if index is None else index
    ch[index:index] = items
    return StructureCommand(doc, [(container, ch)], text)


def delete_items(doc, items, text="Delete"):
    return StructureCommand(doc, ops.remove_items(ops.top_level_only(items)), text)


def replace_item(doc, old: Item, new: Item, text="Convert"):
    par = old.parent
    return StructureCommand(doc, [(par, [new if c is old else c for c in par.children])], text)


def transform_items(doc, items, m: Transform, text="Transform"):
    """Apply a document-space transform to items."""
    return PropertyCommand(doc, [(it, "transform", ops.apply_world(it, m)) for it in items], text)


def move_items(doc, offsets: dict, text="Move"):
    return PropertyCommand(
        doc, [(it, "transform", ops.apply_world(it, Transform.translation(dx, dy))) for it, (dx, dy) in offsets.items()],
        text)


def arrange_items(doc, items, how: str):
    changes = ops.arrange(items, how)
    names = {"front": "Bring to Front", "back": "Send to Back", "forward": "Bring Forward", "backward": "Send Backward"}
    return StructureCommand(doc, changes, names[how]) if changes else None


def group_items(doc, items):
    res = ops.group(doc, items)
    if not res:
        return None, None
    g, changes, transforms = res
    cmds = [PropertyCommand(doc, [(it, "transform", t) for it, t in transforms.items() if t != it.transform]),
            StructureCommand(doc, changes)]
    return Macro("Group", cmds), g


def ungroup_items(doc, groups):
    cmds = []
    children = []
    for g in groups:
        if not isinstance(g, GroupItem):
            continue
        changes, props = ops.ungroup(g)
        children += g.children
        cmds.append(StructureCommand(doc, changes))
        cmds.append(PropertyCommand(doc, [(c, "transform", t) for c, (t, _) in props.items()]
                                    + [(c, "opacity", o) for c, (_, o) in props.items()]))
    return (Macro("Ungroup", cmds), children) if cmds else (None, [])


def add_layer(doc, layer: Layer, index: int | None = None):
    return add_items(doc, doc, [layer], "New Layer", index)
