"""Two-column dockable toolbox with fill/stroke swatches."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QButtonGroup, QDockWidget, QGridLayout, QHBoxLayout, QToolButton, QVBoxLayout,
                               QWidget)

from .icons import icon
from .widgets import FillStrokeSwatch


class Toolbox(QDockWidget):
    def __init__(self, window):
        super().__init__("Tools", window)
        self.setObjectName("toolbox")
        self.window = window
        self.buttons: dict[str, QToolButton] = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        body = QWidget()
        body.setMinimumWidth(84)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 4, 4)
        grid = QGridLayout()
        grid.setSpacing(2)
        for i, tool in enumerate(window.tool_list):
            b = QToolButton()
            b.setCheckable(True)
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(30, 30)
            b.clicked.connect(lambda _=False, n=tool.name: window.set_tool(n))
            self.group.addButton(b)
            self.buttons[tool.name] = b
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        self.swatch = FillStrokeSwatch(window.state)
        self.swatch.targetClicked.connect(lambda t: window.state.set(target=t))
        self.swatch.editRequested.connect(window.choose_color)
        lay.addSpacing(8)
        lay.addWidget(self.swatch, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        row.setSpacing(2)
        self.small: list[tuple[QToolButton, str]] = []
        for name, tip, slot in (("swap", "Swap Fill and Stroke (Shift+X)", window.state.swap),
                                ("rect", "Default Fill and Stroke (D)", window.state.reset_default),
                                ("minus", "None (/)", window.set_paint_none)):
            b = QToolButton()
            b.setToolTip(tip)
            b.setIconSize(QSize(14, 14))
            b.clicked.connect(lambda _=False, s=slot: s())
            row.addWidget(b)
            self.small.append((b, name))
        lay.addLayout(row)
        lay.addStretch(1)
        self.setWidget(body)
        self.retheme()

    def retheme(self) -> None:
        for tool in self.window.tool_list:
            b = self.buttons[tool.name]
            b.setIcon(icon(tool.icon))
            b.setToolTip(f"{tool.label} ({tool.shortcut})" if tool.shortcut else tool.label)
        for b, name in self.small:
            b.setIcon(icon(name, 14))

    def set_active(self, name: str) -> None:
        b = self.buttons.get(name)
        if b:
            b.setChecked(True)
