"""One open document: model, undo stack, scene, view and rulers."""
from __future__ import annotations

import os
import uuid

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGridLayout, QWidget

from ..model.items import Document
from .rulers import RULER_SIZE, Ruler
from .scene import DocumentScene
from .view import CanvasView


class DocumentTab(QWidget):
    _untitled = 0

    def __init__(self, window, doc: Document, path: str | None = None):
        super().__init__()
        self.window = window
        self.doc = doc
        self.path = path
        self.stack = QUndoStack(self)
        self.scene = DocumentScene(doc, self)
        self.view = CanvasView(self)
        self.autosave_id = uuid.uuid4().hex
        self.autosave_dirty = False
        self.force_dirty = False  # recovered documents count as modified
        self.text_editor = None
        if path is None:
            DocumentTab._untitled += 1
            self.untitled_name = f"Untitled-{DocumentTab._untitled}"
        else:
            self.untitled_name = ""
        self.hruler = Ruler(self.view, "h")
        self.vruler = Ruler(self.view, "v")
        self.corner = QWidget()
        self.corner.setFixedSize(RULER_SIZE, RULER_SIZE)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self.corner, 0, 0)
        grid.addWidget(self.hruler, 0, 1)
        grid.addWidget(self.vruler, 1, 0)
        grid.addWidget(self.view, 1, 1)
        self.stack.indexChanged.connect(self._mark_dirty)
        self.scene.selectionChangedSignal.connect(self.view.refresh)

    def _mark_dirty(self, *_):
        self.autosave_dirty = True

    def set_rulers_visible(self, on: bool) -> None:
        for w in (self.hruler, self.vruler, self.corner):
            w.setVisible(on)

    def push(self, cmd) -> None:
        if cmd is not None:
            self.stack.push(cmd)

    def name(self) -> str:
        return os.path.basename(self.path) if self.path else self.untitled_name

    def title(self) -> str:
        return self.name() + (" *" if self.is_modified() else "")

    def is_modified(self) -> bool:
        return self.force_dirty or not self.stack.isClean()

    def is_text_editing(self) -> bool:
        return self.text_editor is not None
