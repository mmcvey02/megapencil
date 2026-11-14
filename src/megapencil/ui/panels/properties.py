"""Properties panel: name, geometry, rotation, opacity, shape / text options."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QFontComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QSlider, QWidget)

from ... import commands as C
from ...model.geometry import Transform
from ...model.items import RectItem, TextItem
from ..widgets import set_quiet, spin


class PropertiesPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._merge = None
        form = QFormLayout(self)
        self.form = form
        self.kind = QLabel("No Selection")
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._name_edited)
        form.addRow(self.kind)
        form.addRow("Name:", self.name)

        self.geo = {}
        for row in (("X", "Y"), ("W", "H")):
            box = QHBoxLayout()
            for key in row:
                s = spin(-100000, 100000, 1, 2, "", 84)
                s.valueChanged.connect(self._geometry_edited)
                self.geo[key] = s
                box.addWidget(QLabel(key))
                box.addWidget(s)
            box.addStretch(1)
            form.addRow(box)

        box = QHBoxLayout()
        self.angle = spin(-360, 360, 15, 1, "°", 84)
        self.angle.setValue(90)
        rot = QPushButton("Rotate")
        rot.clicked.connect(self._rotate)
        box.addWidget(self.angle)
        box.addWidget(rot)
        box.addStretch(1)
        form.addRow("Rotate by:", box)

        box = QHBoxLayout()
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.sliderPressed.connect(lambda: setattr(self, "_merge", window.begin_merge()))
        self.opacity.sliderReleased.connect(lambda: setattr(self, "_merge", None))
        self.opacity.valueChanged.connect(self._opacity_changed)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setMinimumWidth(36)
        box.addWidget(self.opacity, 1)
        box.addWidget(self.opacity_label)
        form.addRow("Opacity:", box)

        self.radius = spin(0, 10000, 1, 1, " px", 100)
        self.radius.valueChanged.connect(lambda v: window.apply_style("corner_radius", v, text="Corner Radius"))
        form.addRow("Corner radius:", self.radius)

        self.font = QFontComboBox()
        self.font.currentFontChanged.connect(lambda f: window.apply_style("font_family", f.family(), text="Font"))
        self.font_size = spin(1, 2000, 1, 1, " px", 100)
        self.font_size.valueChanged.connect(lambda v: window.apply_style("font_size", v, text="Font Size"))
        box = QHBoxLayout()
        self.bold = QCheckBox("Bold")
        self.italic = QCheckBox("Italic")
        self.bold.toggled.connect(lambda v: window.apply_style("bold", v, text="Bold"))
        self.italic.toggled.connect(lambda v: window.apply_style("italic", v, text="Italic"))
        box.addWidget(self.bold)
        box.addWidget(self.italic)
        box.addStretch(1)
        self.style_box = QWidget()
        self.style_box.setLayout(box)
        box.setContentsMargins(0, 0, 0, 0)
        self.text = QPlainTextEdit()
        self.text.setMaximumHeight(70)
        self.text.setTabChangesFocus(True)
        self.apply_text = QPushButton("Apply Text")
        self.apply_text.clicked.connect(self._text_edited)
        form.addRow("Font:", self.font)
        form.addRow("Size:", self.font_size)
        form.addRow("Style:", self.style_box)
        form.addRow("Text:", self.text)
        form.addRow("", self.apply_text)
        self.rect_rows = [self.radius]
        self.text_rows = [self.font, self.font_size, self.style_box, self.text, self.apply_text]
        window.contextChanged.connect(self.refresh)
        self.refresh()

    def _show_rows(self, widgets, on: bool) -> None:
        for w in widgets:
            self.form.setRowVisible(w, on)

    # -- edits --------------------------------------------------------
    def _name_edited(self) -> None:
        tab, sel = self.window.tab, self.window.selection()
        if tab and len(sel) == 1 and sel[0].name != self.name.text():
            tab.push(C.PropertyCommand(tab.doc, [(sel[0], "name", self.name.text())], "Rename"))

    def _geometry_edited(self) -> None:
        g = self.geo
        self.window.apply_geometry(g["X"].value(), g["Y"].value(), g["W"].value(), g["H"].value())

    def _rotate(self) -> None:
        tab, r = self.window.tab, self.window.selection_rect()
        if tab and r is not None and self.angle.value():
            m = Transform.rotation(self.angle.value(), r.center().x(), r.center().y())
            tab.push(C.transform_items(tab.doc, self.window.selection(), m, "Rotate"))

    def _opacity_changed(self, v: int) -> None:
        self.opacity_label.setText(f"{v}%")
        self.window.apply_style("opacity", v / 100, text="Opacity", merge_key=self._merge)

    def _text_edited(self) -> None:
        self.window.apply_style("text", self.text.toPlainText(), text="Edit Text")

    # -- refresh ------------------------------------------------------
    def refresh(self) -> None:
        w = self.window
        sel = w.selection()
        leaves = w.selection_leaves()
        tab = w.tab
        if not sel:
            self.kind.setText(f"Artboard {tab.doc.width:g} × {tab.doc.height:g} px" if tab else "No Document")
        elif len(sel) == 1:
            self.kind.setText(sel[0].kind.capitalize())
        else:
            self.kind.setText(f"{len(sel)} objects")
        self.name.setEnabled(len(sel) == 1)
        if not self.name.hasFocus():
            set_quiet(self.name, sel[0].name if len(sel) == 1 else "")
        rect = w.selection_rect()
        for key, val in zip("XYWH", (rect.x(), rect.y(), rect.width(), rect.height()) if rect else (0, 0, 0, 0)):
            set_quiet(self.geo[key], val)
            self.geo[key].setEnabled(rect is not None)
        self.opacity.setEnabled(bool(sel))
        set_quiet(self.opacity, round(sel[0].opacity * 100) if sel else 100)
        self.opacity_label.setText(f"{self.opacity.value()}%")
        rects = [i for i in leaves[:50] if isinstance(i, RectItem)]
        texts = [i for i in leaves[:50] if isinstance(i, TextItem)]
        self._show_rows(self.rect_rows, bool(rects))
        self._show_rows(self.text_rows, bool(texts))
        if rects:
            set_quiet(self.radius, rects[0].rx)
        if texts:
            t = texts[0]
            self.font.blockSignals(True)
            self.font.setCurrentFont(QFont(t.font_family))
            self.font.blockSignals(False)
            set_quiet(self.font_size, t.font_size)
            set_quiet(self.bold, t.bold)
            set_quiet(self.italic, t.italic)
            if not self.text.hasFocus():
                self.text.blockSignals(True)
                self.text.setPlainText(t.text)
                self.text.blockSignals(False)
