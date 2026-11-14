"""Color panel: fill / stroke target, RGB + alpha sliders, HEX, swatches, gradients."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton,
                               QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from ...model.paint import BLACK, WHITE, Color, Gradient, GradientStop
from ..icons import icon
from ..qtbridge import make_brush
from ..widgets import paint_icon, set_quiet, spin

TYPES = ["None", "Solid", "Linear Gradient", "Radial Gradient"]
SWATCHES = ["#000000", "#404040", "#808080", "#c0c0c0", "#ffffff", "#7f1d1d", "#e02020", "#ff6f61",
            "#f08c00", "#ffd24a", "#fff3a3", "#3f6212", "#2e9e44", "#8fd694", "#0f766e", "#20c5b5",
            "#7fe3ff", "#1e3a8a", "#2f80ed", "#93c5fd", "#4c1d95", "#8b5cf6", "#d8b4fe", "#9d174d",
            "#ec4899", "#f9a8d4", "#5c4033", "#a0714f", "#e7c9a9", "#16102e", "#3b2a7a", "#ff00ff"]


class ColorPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.state = window.state
        self.stop_index = 0
        self._merge = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        row = QHBoxLayout()
        self.target = QButtonGroup(self)
        self.fill_radio = QRadioButton("Fill")
        self.stroke_radio = QRadioButton("Stroke")
        for b, name in ((self.fill_radio, "fill"), (self.stroke_radio, "stroke")):
            self.target.addButton(b)
            b.toggled.connect(lambda on, n=name: on and self.state.set(target=n))
            row.addWidget(b)
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.type.currentIndexChanged.connect(self._type_changed)
        row.addWidget(self.type, 1)
        lay.addLayout(row)

        # gradient editor
        self.gradient_box = QWidget()
        g = QVBoxLayout(self.gradient_box)
        g.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel()
        self.preview.setFixedHeight(18)
        g.addWidget(self.preview)
        row = QHBoxLayout()
        self.stop = QComboBox()
        self.stop.currentIndexChanged.connect(self._stop_selected)
        self.offset = spin(0, 100, 5, 0, " %", 70)
        self.offset.valueChanged.connect(self._offset_changed)
        self.add_stop = QToolButton()
        self.add_stop.setToolTip("Add gradient stop")
        self.add_stop.clicked.connect(self._add_stop)
        self.del_stop = QToolButton()
        self.del_stop.setToolTip("Remove gradient stop")
        self.del_stop.clicked.connect(self._remove_stop)
        for w in (self.stop, self.offset, self.add_stop, self.del_stop):
            row.addWidget(w)
        g.addLayout(row)
        row = QHBoxLayout()
        self.angle_label = QLabel("Angle")
        self.angle = spin(-360, 360, 15, 0, "°", 70)
        self.angle.valueChanged.connect(self._angle_changed)
        row.addWidget(self.angle_label)
        row.addWidget(self.angle)
        row.addStretch(1)
        g.addLayout(row)
        lay.addWidget(self.gradient_box)

        # channels
        grid = QGridLayout()
        self.sliders, self.boxes = {}, {}
        for r, ch in enumerate("RGBA"):
            s = QSlider(Qt.Horizontal)
            s.setRange(0, 255 if ch != "A" else 100)
            b = QSpinBox()
            b.setRange(0, 255 if ch != "A" else 100)
            b.setKeyboardTracking(False)
            s.sliderPressed.connect(lambda: setattr(self, "_merge", window.begin_merge()))
            s.sliderReleased.connect(lambda: setattr(self, "_merge", None))
            s.valueChanged.connect(lambda v, c=ch: self._channel_changed(c, v))
            b.valueChanged.connect(lambda v, c=ch: self._channel_changed(c, v))
            grid.addWidget(QLabel(ch), r, 0)
            grid.addWidget(s, r, 1)
            grid.addWidget(b, r, 2)
            self.sliders[ch], self.boxes[ch] = s, b
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(QLabel("HEX"))
        self.hex = QLineEdit()
        self.hex.setMaxLength(9)
        self.hex.editingFinished.connect(self._hex_edited)
        row.addWidget(self.hex, 1)
        lay.addLayout(row)

        grid = QGridLayout()
        grid.setSpacing(1)
        for i, h in enumerate(SWATCHES):
            b = QToolButton()
            b.setIconSize(QSize(16, 16))
            b.setIcon(paint_icon(Color.parse(h), 16))
            b.setToolTip(h.upper())
            b.setAutoRaise(True)
            b.clicked.connect(lambda _=False, c=Color.parse(h): self.set_color(c))
            grid.addWidget(b, i // 8, i % 8)
        lay.addLayout(grid)
        lay.addStretch(1)
        self.retheme()
        self.state.changed.connect(self.refresh)
        window.contextChanged.connect(self.refresh)
        self.refresh()

    def retheme(self) -> None:
        self.add_stop.setIcon(icon("plus", 14))
        self.del_stop.setIcon(icon("minus", 14))

    # -- model access -------------------------------------------------
    def paint(self):
        return getattr(self.state, self.state.target)

    def current_color(self) -> Color:
        p = self.paint()
        if isinstance(p, Gradient):
            return p.stops[min(self.stop_index, len(p.stops) - 1)].color
        return p if isinstance(p, Color) else BLACK

    def apply(self, paint, text: str = "Color") -> None:
        self.window.apply_style(self.state.target, paint, text=f"{self.state.target.capitalize()} {text}",
                                merge_key=self._merge)

    def set_color(self, c: Color) -> None:
        p = self.paint()
        if isinstance(p, Gradient):
            stops = list(p.stops)
            i = min(self.stop_index, len(stops) - 1)
            stops[i] = GradientStop(stops[i].offset, c)
            self.apply(replace(p, stops=tuple(stops)), "Gradient")
        else:
            self.apply(c)

    # -- widget slots -------------------------------------------------
    def _type_changed(self, i: int) -> None:
        p = self.paint()
        cur = self.current_color()
        if i == 0:
            self.apply(None)
        elif i == 1:
            self.apply(p.first_color() if isinstance(p, Gradient) else cur)
        else:
            stops = p.stops if isinstance(p, Gradient) else (
                GradientStop(0.0, cur), GradientStop(1.0, WHITE if cur != WHITE else BLACK))
            self.stop_index = 0
            angle = p.angle() if isinstance(p, Gradient) and p.kind == "linear" else 0.0
            self.apply(Gradient.linear(stops, angle) if i == 2 else Gradient.radial(stops), "Gradient")

    def _channel_changed(self, ch: str, v: int) -> None:
        c = self.current_color()
        new = {"R": Color(v, c.g, c.b, c.a), "G": Color(c.r, v, c.b, c.a), "B": Color(c.r, c.g, v, c.a),
               "A": Color(c.r, c.g, c.b, v / 100)}[ch]
        if new != c or self.paint() is None:
            self.set_color(new)

    def _hex_edited(self) -> None:
        text = self.hex.text().strip()
        c = Color.parse(text if text.startswith("#") else "#" + text)
        if c is None:
            self.window.status_message("Enter a colour as #RRGGBB.")
            self.refresh()
        elif c != self.current_color() or self.paint() is None:
            self.set_color(c.with_alpha(self.current_color().a) if len(text.lstrip("#")) <= 6 else c)

    def _stop_selected(self, i: int) -> None:
        if i >= 0:
            self.stop_index = i
            self.refresh()

    def _offset_changed(self, v: float) -> None:
        p = self.paint()
        if isinstance(p, Gradient):
            stops = list(p.stops)
            i = min(self.stop_index, len(stops) - 1)
            stops[i] = GradientStop(v / 100, stops[i].color)
            order = sorted(range(len(stops)), key=lambda k: stops[k].offset)
            self.stop_index = order.index(i)
            self.apply(replace(p, stops=tuple(stops[k] for k in order)), "Gradient")

    def _add_stop(self) -> None:
        p = self.paint()
        if isinstance(p, Gradient):
            stops = list(p.stops)
            i = min(self.stop_index, len(stops) - 1)
            j = i + 1 if i + 1 < len(stops) else i - 1
            a, b = stops[min(i, j)], stops[max(i, j)]
            mid = GradientStop((a.offset + b.offset) / 2,
                               Color((a.color.r + b.color.r) // 2, (a.color.g + b.color.g) // 2,
                                     (a.color.b + b.color.b) // 2, (a.color.a + b.color.a) / 2))
            stops.insert(max(i, j), mid)
            self.stop_index = max(i, j)
            self.apply(replace(p, stops=tuple(stops)), "Gradient")

    def _remove_stop(self) -> None:
        p = self.paint()
        if isinstance(p, Gradient) and len(p.stops) > 2:
            stops = list(p.stops)
            del stops[min(self.stop_index, len(stops) - 1)]
            self.stop_index = max(0, self.stop_index - 1)
            self.apply(replace(p, stops=tuple(stops)), "Gradient")

    def _angle_changed(self, v: float) -> None:
        p = self.paint()
        if isinstance(p, Gradient) and p.kind == "linear":
            self.apply(Gradient.linear(p.stops, v), "Gradient")

    # -- refresh ------------------------------------------------------
    def refresh(self) -> None:
        p = self.paint()
        set_quiet(self.fill_radio if self.state.target == "fill" else self.stroke_radio, True)
        is_grad = isinstance(p, Gradient)
        idx = 0 if p is None else 1 if isinstance(p, Color) else 2 if p.kind == "linear" else 3
        self.type.blockSignals(True)
        self.type.setCurrentIndex(idx)
        self.type.blockSignals(False)
        self.gradient_box.setVisible(is_grad)
        if is_grad:
            self.stop_index = min(self.stop_index, len(p.stops) - 1)
            self.stop.blockSignals(True)
            self.stop.clear()
            self.stop.addItems([f"Stop {i + 1}" for i in range(len(p.stops))])
            self.stop.setCurrentIndex(self.stop_index)
            self.stop.blockSignals(False)
            set_quiet(self.offset, p.stops[self.stop_index].offset * 100)
            self.del_stop.setEnabled(len(p.stops) > 2)
            self.angle.setVisible(p.kind == "linear")
            self.angle_label.setVisible(p.kind == "linear")
            if p.kind == "linear":
                set_quiet(self.angle, round(p.angle()))
            w = max(self.preview.width(), 60)
            pm = QPixmap(w, 18)
            pm.fill(Qt.white)
            painter = QPainter(pm)
            painter.fillRect(QRectF(0, 0, w, 18), make_brush(Gradient.linear(p.stops, 0), QRectF(0, 0, w, 18)))
            painter.end()
            self.preview.setPixmap(pm)
        c = self.current_color()
        for ch, v in zip("RGBA", (c.r, c.g, c.b, round(c.a * 100))):
            set_quiet(self.sliders[ch], v)
            set_quiet(self.boxes[ch], v)
        if not self.hex.hasFocus():
            set_quiet(self.hex, c.to_hex().upper() if p is not None else "")
