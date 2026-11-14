"""Layers panel: add, delete, reorder, rename, show/hide, lock, opacity."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QSlider, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ... import commands as C
from ...model.items import Layer
from ..icons import icon


class LayersPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._building = False
        self._signature = None
        self._merge = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.header().setMinimumSectionSize(24)
        self.tree.setColumnWidth(0, 28)
        self.tree.setColumnWidth(1, 28)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemChanged.connect(self._renamed)
        self.tree.currentItemChanged.connect(self._current_changed)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Opacity"))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.sliderPressed.connect(lambda: setattr(self, "_merge", window.begin_merge()))
        self.opacity.sliderReleased.connect(lambda: setattr(self, "_merge", None))
        self.opacity.valueChanged.connect(self._opacity_changed)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setMinimumWidth(36)
        row.addWidget(self.opacity, 1)
        row.addWidget(self.opacity_label)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.buttons = []
        for name, tip, slot in (("plus", "New Layer", self.add_layer), ("minus", "Delete Layer", self.delete_layer),
                                ("up", "Move Layer Up", lambda: self.move_layer(1)),
                                ("down", "Move Layer Down", lambda: self.move_layer(-1))):
            b = QToolButton()
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, s=slot: s())
            row.addWidget(b)
            self.buttons.append((b, name))
        row.addStretch(1)
        lay.addLayout(row)
        self.retheme()
        window.contextChanged.connect(self.refresh)

    def retheme(self) -> None:
        for b, name in self.buttons:
            b.setIcon(icon(name, 16))
        self._signature = None
        self.refresh()

    # -- helpers ------------------------------------------------------
    def _tab(self):
        return self.window.tab

    def _layer_of(self, item: QTreeWidgetItem | None) -> Layer | None:
        return item.data(2, Qt.UserRole) if item is not None else None

    def current_layer(self) -> Layer | None:
        tab = self._tab()
        return tab.scene.active_layer if tab else None

    def refresh(self) -> None:
        tab = self._tab()
        layers = list(reversed(tab.doc.layers)) if tab else []
        active = tab.scene.active_layer if tab else None
        sig = (id(tab), id(active), tuple((id(l), l.name, l.visible, l.locked, len(l.children)) for l in layers))
        if sig != self._signature:
            self._signature = sig
            self._building = True
            self.tree.clear()
            for layer in layers:
                it = QTreeWidgetItem()
                it.setData(2, Qt.UserRole, layer)
                it.setText(2, layer.name)
                it.setToolTip(2, f"{len(layer.children)} object(s)")
                it.setIcon(0, icon("eye", 16) if layer.visible else QIcon())
                it.setIcon(1, icon("lock", 16) if layer.locked else QIcon())
                it.setToolTip(0, "Show / hide layer")
                it.setToolTip(1, "Lock / unlock layer")
                it.setFlags(it.flags() | Qt.ItemIsEditable)
                self.tree.addTopLevelItem(it)
                if layer is active:
                    self.tree.setCurrentItem(it)
            self._building = False
        self.opacity.setEnabled(active is not None)
        if active is not None:
            self.opacity.blockSignals(True)
            self.opacity.setValue(round(active.opacity * 100))
            self.opacity.blockSignals(False)
            self.opacity_label.setText(f"{round(active.opacity * 100)}%")

    # -- interaction --------------------------------------------------
    def _clicked(self, item: QTreeWidgetItem, column: int) -> None:
        tab, layer = self._tab(), self._layer_of(item)
        if not tab or layer is None:
            return
        if column == 0:
            tab.push(C.PropertyCommand(tab.doc, [(layer, "visible", not layer.visible)],
                                       "Show Layer" if not layer.visible else "Hide Layer"))
        elif column == 1:
            tab.push(C.PropertyCommand(tab.doc, [(layer, "locked", not layer.locked)],
                                       "Lock Layer" if not layer.locked else "Unlock Layer"))
        if column in (0, 1) and not layer.editable():
            tab.scene.set_selection([i for i in tab.scene.selection if i.layer() is not layer])

    def _current_changed(self, item, _prev) -> None:
        tab, layer = self._tab(), self._layer_of(item)
        if self._building or not tab or layer is None:
            return
        tab.scene.active_layer = layer
        self.window.refresh_context()

    def _renamed(self, item: QTreeWidgetItem, column: int) -> None:
        tab, layer = self._tab(), self._layer_of(item)
        if self._building or column != 2 or not tab or layer is None:
            return
        name = item.text(2).strip() or layer.name
        if name != layer.name:
            tab.push(C.PropertyCommand(tab.doc, [(layer, "name", name)], "Rename Layer"))

    def _opacity_changed(self, value: int) -> None:
        tab, layer = self._tab(), self.current_layer()
        self.opacity_label.setText(f"{value}%")
        if tab and layer is not None and abs(layer.opacity - value / 100) > 1e-9:
            tab.push(C.PropertyCommand(tab.doc, [(layer, "opacity", value / 100)], "Layer Opacity", self._merge))

    # -- commands -----------------------------------------------------
    def add_layer(self) -> Layer | None:
        tab = self._tab()
        if not tab:
            return None
        names = {l.name for l in tab.doc.layers}
        n = len(tab.doc.layers) + 1
        while f"Layer {n}" in names:
            n += 1
        layer = Layer(f"Layer {n}")
        cur = self.current_layer()
        index = tab.doc.layers.index(cur) + 1 if cur in tab.doc.layers else None
        tab.push(C.add_layer(tab.doc, layer, index))
        tab.scene.active_layer = layer
        self.window.refresh_context()
        return layer

    def delete_layer(self) -> None:
        tab, layer = self._tab(), self.current_layer()
        if not tab or layer is None:
            return
        if len(tab.doc.layers) <= 1:
            self.window.status_message("A document needs at least one layer.")
            return
        tab.push(C.StructureCommand(tab.doc, [(tab.doc, [l for l in tab.doc.layers if l is not layer])],
                                    "Delete Layer"))

    def move_layer(self, step: int) -> None:
        tab, layer = self._tab(), self.current_layer()
        if not tab or layer is None:
            return
        layers = list(tab.doc.layers)
        i = layers.index(layer)
        j = i + step
        if 0 <= j < len(layers):
            layers[i], layers[j] = layers[j], layers[i]
            tab.push(C.StructureCommand(tab.doc, [(tab.doc, layers)], "Reorder Layers"))
