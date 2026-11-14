"""Text tool: point text with an in-place editor."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFontMetricsF, QTextOption
from PySide6.QtWidgets import QFrame, QPlainTextEdit

from ... import commands as C
from ...model.items import TextItem
from ..qtbridge import make_font
from .base import Tool


class TextEditor(QPlainTextEdit):
    """Overlay editor placed on the canvas at the text's position."""

    def __init__(self, tool, view, item: TextItem, is_new: bool):
        super().__init__(view.viewport())
        self.tool, self.view, self.item, self.is_new = tool, view, item, is_new
        self.done = False
        self.setFrameShape(QFrame.NoFrame)
        self.setWordWrapMode(QTextOption.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.setStyleSheet("QPlainTextEdit { background: rgba(255,255,255,235); color: black;"
                           " border: 1px solid #2f80ed; }")
        self.setPlainText(item.text)
        self.textChanged.connect(self.reposition)
        self.reposition()
        self.show()
        self.setFocus()
        self.selectAll() if not is_new else None

    def reposition(self) -> None:
        it, view = self.item, self.view
        scale = it.world_transform().mean_scale() * view.zoom
        font, _ = make_font(it.font_family, max(1.0, it.font_size * scale), it.bold, it.italic)
        self.setFont(font)
        fm = QFontMetricsF(font)
        lines = self.toPlainText().split("\n")
        w = max([fm.horizontalAdvance(line) for line in lines] + [fm.averageCharWidth() * 2]) + 12
        h = fm.lineSpacing() * max(1, len(lines)) + 6
        origin = view.to_view(QPointF(*it.world_transform().map(it.x, it.y)))
        self.setGeometry(int(origin.x()) - 1, int(origin.y() - fm.ascent()) - 1, int(w), int(h))

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Escape:
            self.cancel()
        elif ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() & Qt.ControlModifier:
            self.commit()
        else:
            super().keyPressEvent(ev)

    def focusOutEvent(self, ev) -> None:
        super().focusOutEvent(ev)
        if ev.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            self.commit()

    def commit(self) -> None:
        if not self.done:
            self.done = True
            self.tool.finish(self, self.toPlainText())

    def cancel(self) -> None:
        if not self.done:
            self.done = True
            self.tool.finish(self, None)


class TextTool(Tool):
    name, label, shortcut, icon = "text", "Text", "T", "text"
    cursor = Qt.IBeamCursor

    def deactivate(self, view) -> None:
        if view.tab.text_editor is not None:
            view.tab.text_editor.commit()

    def mouse_press(self, view, ev, pos):
        tab = view.tab
        if tab.text_editor is not None:
            tab.text_editor.commit()
            return
        hit = tab.scene.item_at(pos, view.px(3), deep=True)
        if isinstance(hit, TextItem):
            self.edit_item(view, hit)
            return
        if self.target_layer(view) is None:
            return
        st = self.window.state
        item = TextItem(x=pos.x(), y=pos.y(), font_family=st.font_family, font_size=st.font_size)
        if st.fill is not None:
            item.fill = st.fill
        self._open(view, item, True)

    def edit_item(self, view, item: TextItem) -> None:
        tab = view.tab
        if tab.text_editor is not None:
            tab.text_editor.commit()
        tab.scene.set_selection([item])
        g = tab.scene.graphics.get(id(item))
        if g:
            g.setVisible(False)
        self._open(view, item, False)

    def _open(self, view, item: TextItem, is_new: bool) -> None:
        view.tab.text_editor = TextEditor(self, view, item, is_new)

    def finish(self, editor: TextEditor, text: str | None) -> None:
        view, item = editor.view, editor.item
        tab = view.tab
        tab.text_editor = None
        editor.hide()
        editor.deleteLater()
        g = tab.scene.graphics.get(id(item))
        if g:
            g.sync()
        if text is not None:
            text = text.rstrip("\n")
            if editor.is_new:
                layer = self.target_layer(view)
                if text.strip() and layer is not None:
                    item.text = text
                    tab.push(C.add_items(tab.doc, layer, [item], "Add Text"))
                    tab.scene.set_selection([item])
            elif not text.strip():
                tab.push(C.delete_items(tab.doc, [item], "Delete Text"))
            elif text != item.text:
                tab.push(C.PropertyCommand(tab.doc, [(item, "text", text)], "Edit Text"))
        view.setFocus()
        view.refresh()
