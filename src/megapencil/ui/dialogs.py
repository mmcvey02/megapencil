"""Dialogs: new document, export, preferences, shortcuts, about."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import APP_NAME, __version__
from .widgets import spin

PRESETS = [("Custom", None), ("Web 1280 × 720", (1280, 720)), ("Web 1920 × 1080", (1920, 1080)),
           ("A4 (96 dpi)", (794, 1123)), ("Letter (96 dpi)", (816, 1056)), ("Square 1024", (1024, 1024)),
           ("Icon 256", (256, 256))]


def _buttons(dlg: QDialog) -> QDialogButtonBox:
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


class DocumentSizeDialog(QDialog):
    def __init__(self, parent, title: str, width: float, height: float):
        super().__init__(parent)
        self.setWindowTitle(title)
        form = QFormLayout(self)
        self.preset = QComboBox()
        for name, _ in PRESETS:
            self.preset.addItem(name)
        self.w = spin(1, 20000, 10, 0, " px", 110)
        self.h = spin(1, 20000, 10, 0, " px", 110)
        self.w.setValue(width)
        self.h.setValue(height)
        self.preset.currentIndexChanged.connect(self._preset)
        form.addRow("Preset:", self.preset)
        form.addRow("Width:", self.w)
        form.addRow("Height:", self.h)
        form.addRow(_buttons(self))

    def _preset(self, i: int) -> None:
        size = PRESETS[i][1]
        if size:
            self.w.setValue(size[0])
            self.h.setValue(size[1])

    def size_values(self) -> tuple[float, float]:
        return self.w.value(), self.h.value()


class ExportDialog(QDialog):
    def __init__(self, parent, kind: str, width: float, height: float):
        super().__init__(parent)
        self.setWindowTitle(f"Export {kind}")
        self._size = (width, height)
        form = QFormLayout(self)
        self.scale = spin(0.05, 32, 0.5, 2, " ×", 110)
        self.scale.setValue(1.0)
        self.info = QLabel()
        self.transparent = QCheckBox("Transparent background")
        self.transparent.setChecked(True)
        self.scale.valueChanged.connect(self._update)
        form.addRow("Scale:", self.scale)
        form.addRow("Output size:", self.info)
        if kind == "PNG":
            form.addRow(self.transparent)
        form.addRow(_buttons(self))
        self._kind = kind
        self._update()

    def _update(self) -> None:
        s = self.scale.value()
        unit = "px" if self._kind == "PNG" else "pt"
        k = s if self._kind == "PNG" else s * 0.75
        self.info.setText(f"{self._size[0] * k:.0f} × {self._size[1] * k:.0f} {unit}")


class PreferencesDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.settings = settings
        form = QFormLayout(self)
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(settings.get("theme"))
        self.autosave = QCheckBox("Autosave modified documents")
        self.autosave.setChecked(settings.get("autosave_enabled"))
        self.interval = QSpinBox()
        self.interval.setRange(10, 3600)
        self.interval.setSuffix(" s")
        self.interval.setValue(settings.get("autosave_interval"))
        self.nudge = spin(0.01, 1000, 1, 2, " px", 110)
        self.nudge.setValue(settings.get("nudge"))
        self.big_nudge = spin(0.01, 1000, 1, 2, " px", 110)
        self.big_nudge.setValue(settings.get("big_nudge"))
        self.dw = QSpinBox()
        self.dh = QSpinBox()
        for s, key in ((self.dw, "default_width"), (self.dh, "default_height")):
            s.setRange(1, 20000)
            s.setSuffix(" px")
            s.setValue(settings.get(key))
        self.recent = QSpinBox()
        self.recent.setRange(0, 30)
        self.recent.setValue(settings.get("max_recent"))
        form.addRow("Theme:", self.theme)
        form.addRow(self.autosave)
        form.addRow("Autosave interval:", self.interval)
        form.addRow("Arrow-key nudge:", self.nudge)
        form.addRow("Shift + arrow nudge:", self.big_nudge)
        form.addRow("New document width:", self.dw)
        form.addRow("New document height:", self.dh)
        form.addRow("Recent files to keep:", self.recent)
        form.addRow(_buttons(self))

    def apply(self) -> None:
        s = self.settings
        s.set("theme", self.theme.currentText())
        s.set("autosave_enabled", self.autosave.isChecked())
        s.set("autosave_interval", self.interval.value())
        s.set("nudge", self.nudge.value())
        s.set("big_nudge", self.big_nudge.value())
        s.set("default_width", self.dw.value())
        s.set("default_height", self.dh.value())
        s.set("max_recent", self.recent.value())


EXTRA_SHORTCUTS = [
    ("Canvas", "Pan", "Space + drag, middle-button drag"),
    ("Canvas", "Zoom at cursor", "Ctrl + mouse wheel"),
    ("Canvas", "Create guide", "Drag from a ruler"),
    ("Selection tool", "Add to / remove from selection", "Shift + click"),
    ("Selection tool", "Constrain move / proportional scale / 15° rotate", "Shift + drag"),
    ("Selection tool", "Scale from centre", "Alt + drag handle"),
    ("Selection tool", "Duplicate while moving", "Alt + drag"),
    ("Selection tool", "Nudge / big nudge", "Arrow keys / Shift + arrow keys"),
    ("Shape tools", "Square, circle, 45° line", "Shift + drag"),
    ("Shape tools", "Draw from centre", "Alt + drag"),
    ("Pen tool", "Corner point / smooth point", "Click / click-drag"),
    ("Pen tool", "Finish open path", "Enter or Esc"),
    ("Pen tool", "Close path", "Click the first anchor"),
    ("Pen tool", "Remove last point", "Ctrl+Z or Backspace"),
    ("Direct Selection", "Convert anchor (corner ↔ smooth)", "Alt + click anchor"),
    ("Direct Selection", "Break handle symmetry", "Alt + drag handle"),
    ("Text tool", "Commit text / cancel", "Ctrl+Enter or click away / Esc"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent, rows: list[tuple[str, str, str]]):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["Area", "Command", "Shortcut"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(text))
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.resizeColumnToContents(0)
        table.resizeColumnToContents(2)
        self.table = table
        lay.addWidget(table)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


ABOUT_HTML = f"""<h2>{APP_NAME} {__version__}</h2>
<p>A vector graphics editor for the Linux desktop.</p>
<p>Native format: SVG.  Built with Python and Qt (PySide6).<br>
Boolean path operations use the Clipper library (pyclipper).</p>
<p>{APP_NAME} is an original, independent project and works entirely offline.</p>"""
