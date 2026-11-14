"""Align and distribute panel."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from ... import commands as C
from ...model import ops
from ..icons import icon

ALIGN = [("left", "Align Left Edges"), ("hcenter", "Align Horizontal Centers"), ("right", "Align Right Edges"),
         ("top", "Align Top Edges"), ("vcenter", "Align Vertical Centers"), ("bottom", "Align Bottom Edges")]
DISTRIBUTE = [("hcenters", "Distribute Horizontal Centers"), ("vcenters", "Distribute Vertical Centers"),
              ("hspace", "Distribute Horizontal Spacing"), ("vspace", "Distribute Vertical Spacing")]


class AlignPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.buttons = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(QLabel("Align Objects"))
        grid = QGridLayout()
        for i, (mode, tip) in enumerate(ALIGN):
            grid.addWidget(self._button(f"align_{mode}", tip, lambda m=mode: self.align(m)), 0, i)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Distribute Objects"))
        grid = QGridLayout()
        for i, (mode, tip) in enumerate(DISTRIBUTE):
            grid.addWidget(self._button(f"dist_{mode}", tip, lambda m=mode: self.distribute(m)), 0, i)
        grid.setColumnStretch(len(DISTRIBUTE), 1)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Align To"))
        self.relative = QComboBox()
        self.relative.addItems(["Selection", "Artboard"])
        lay.addWidget(self.relative)
        lay.addStretch(1)
        self.retheme()

    def _button(self, icon_name: str, tip: str, slot) -> QToolButton:
        b = QToolButton()
        b.setToolTip(tip)
        b.setIconSize(QSize(20, 20))
        b.clicked.connect(lambda _=False: slot())
        self.buttons.append((b, icon_name))
        return b

    def retheme(self) -> None:
        for b, name in self.buttons:
            b.setIcon(icon(name, 20))

    def _apply(self, offsets: dict, text: str) -> None:
        tab = self.window.tab
        if tab and offsets:
            tab.push(C.move_items(tab.doc, offsets, text))

    def align(self, mode: str) -> None:
        tab = self.window.tab
        if not tab:
            return
        items = ops.top_level_only(self.window.selection())
        ref = (0.0, 0.0, tab.doc.width, tab.doc.height) if self.relative.currentText() == "Artboard" else None
        if ref is None and len(items) < 2:
            self.window.status_message("Select two or more objects, or align to the artboard.")
            return
        self._apply(ops.align(items, mode, ref), "Align")

    def distribute(self, mode: str) -> None:
        items = ops.top_level_only(self.window.selection())
        if len(items) < 3:
            self.window.status_message("Select three or more objects to distribute.")
            return
        self._apply(ops.distribute(items, mode), "Distribute")
