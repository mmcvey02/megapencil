"""Context-sensitive control bar below the menu."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFontComboBox, QLabel, QToolBar

from ..model.items import RectItem, TextItem
from .widgets import PaintButton, set_quiet, spin


class ControlBar(QToolBar):
    def __init__(self, window):
        super().__init__("Control", window)
        self.setObjectName("controlbar")
        self.window = window
        self.setMovable(False)
        self.context = QLabel("No Selection")
        self.context.setMinimumWidth(110)
        self.addWidget(self.context)
        self.addSeparator()

        self.fill = PaintButton("Fill")
        self.fill.clicked.connect(lambda: window.choose_color("fill"))
        self.stroke = PaintButton("Stroke")
        self.stroke.clicked.connect(lambda: window.choose_color("stroke"))
        self.width = spin(0, 1000, 0.5, 2, " px", 80)
        self.width.valueChanged.connect(lambda v: window.apply_style("stroke_width", v, text="Stroke Width"))
        self._add("Fill", self.fill)
        self._add("Stroke", self.stroke)
        self._add("", self.width)
        self.addSeparator()

        self.geo = {}
        for key in ("X", "Y", "W", "H"):
            s = spin(-100000, 100000, 1, 2, "", 78)
            s.valueChanged.connect(self._geometry_edited)
            self.geo[key] = s
            self._add(key, s)
        self.addSeparator()
        self.opacity = spin(0, 100, 5, 0, " %", 70)
        self.opacity.valueChanged.connect(lambda v: window.apply_style("opacity", v / 100, text="Opacity"))
        self._add("Opacity", self.opacity)

        self.radius = spin(0, 10000, 1, 1, " px", 76)
        self.radius.valueChanged.connect(lambda v: window.apply_style("corner_radius", v, text="Corner Radius"))
        self.radius_actions = [self.addSeparator(), *self._add("Corners", self.radius)]

        self.font = QFontComboBox()
        self.font.setMaximumWidth(170)
        self.font.currentFontChanged.connect(lambda f: window.apply_style("font_family", f.family(), text="Font"))
        self.font_size = spin(1, 2000, 1, 1, " px", 76)
        self.font_size.valueChanged.connect(lambda v: window.apply_style("font_size", v, text="Font Size"))
        self.font_actions = [self.addSeparator(), *self._add("Font", self.font), *self._add("", self.font_size)]
        window.contextChanged.connect(self.refresh)
        window.state.changed.connect(self.refresh)

    def _add(self, label: str, widget):
        acts = []
        if label:
            acts.append(self.addWidget(QLabel(f" {label}: ")))
        acts.append(self.addWidget(widget))
        return acts

    def _geometry_edited(self) -> None:
        g = self.geo
        self.window.apply_geometry(g["X"].value(), g["Y"].value(), g["W"].value(), g["H"].value())

    def refresh(self) -> None:
        w = self.window
        st = w.state
        sel = w.selection()
        tool = w.tool.name if w.tool else ""
        if not sel:
            self.context.setText(f"{w.tool.label} Tool" if w.tool else "No Selection")
        elif len(sel) == 1:
            self.context.setText(sel[0].display_name())
        else:
            self.context.setText(f"{len(sel)} Objects")
        self.fill.set_paint(st.fill)
        self.stroke.set_paint(st.stroke)
        set_quiet(self.width, st.stroke_width)
        rect = w.selection_rect()
        for key, val in zip("XYWH", (rect.x(), rect.y(), rect.width(), rect.height()) if rect else (0, 0, 0, 0)):
            set_quiet(self.geo[key], val)
            self.geo[key].setEnabled(rect is not None)
        self.opacity.setEnabled(bool(sel))
        set_quiet(self.opacity, round(sel[0].opacity * 100) if sel else 100)
        leaves = w.selection_leaves()
        show_radius = tool == "rect" or any(isinstance(i, RectItem) for i in leaves[:50])
        show_font = tool == "text" or any(isinstance(i, TextItem) for i in leaves[:50])
        for a in self.radius_actions:
            a.setVisible(show_radius)
        for a in self.font_actions:
            a.setVisible(show_font)
        set_quiet(self.radius, st.corner_radius)
        self.font.blockSignals(True)
        self.font.setCurrentFont(QFont(st.font_family))
        self.font.blockSignals(False)
        set_quiet(self.font_size, st.font_size)
