"""Main window: menus, docks, document tabs and all document-level commands."""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QColorDialog, QDockWidget, QFileDialog, QFontDialog, QLabel,
                               QMainWindow, QMessageBox, QTabWidget)

from .. import APP_NAME
from .. import commands as C
from ..model import ops, svgio
from ..model.boolean import boolean_op
from ..model.geometry import Transform
from ..model.items import Document, GroupItem, Item, PathItem, RectItem, TextItem
from ..model.paint import Color, Gradient
from ..settings import Settings
from . import theme
from .autosave import AutosaveManager
from .controlbar import ControlBar
from .dialogs import (ABOUT_HTML, EXTRA_SHORTCUTS, DocumentSizeDialog, ExportDialog, PreferencesDialog,
                      ShortcutsDialog)
from .docwidget import DocumentTab
from .export import export_pdf, export_png
from .panels import PANELS
from .qtbridge import from_qcolor, install_text_outliner, make_font, qcolor
from .state import AppState
from .toolbox import Toolbox
from .tools import TOOL_CLASSES

TEXT_ATTRS = ("font_family", "font_size", "bold", "italic")
SVG_FILTER = "SVG files (*.svg);;All files (*)"


class MainWindow(QMainWindow):
    contextChanged = Signal()

    def __init__(self, settings: Settings | None = None, interactive: bool = True):
        super().__init__()
        install_text_outliner()
        self.interactive = interactive  # False in tests: never block on dialogs
        self.settings = settings or Settings()
        self.state = AppState()
        self.clipboard: list[Item] = []
        self.paste_count = 0
        self._merge_serial = 0
        self.tool_list = [cls(self) for cls in TOOL_CLASSES]
        self.tools = {t.name: t for t in self.tool_list}
        self.tool = None
        self._ctx_timer = QTimer(self)
        self._ctx_timer.setSingleShot(True)
        self._ctx_timer.timeout.connect(self.contextChanged.emit)

        theme.apply_theme(QApplication.instance(), self.settings.get("theme"))
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)
        self.setDockNestingEnabled(True)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tab_widget)

        self.actions_by_area: list[tuple[str, QAction]] = []
        self._build_menus()
        self.controlbar = ControlBar(self)
        self.addToolBar(Qt.TopToolBarArea, self.controlbar)
        self.toolbox = Toolbox(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.toolbox)
        self.panels: dict[str, object] = {}
        self.docks: list[QDockWidget] = [self.toolbox]
        prev = None
        for title, name, cls in PANELS:
            dock = QDockWidget(title, self)
            dock.setObjectName(name)
            panel = cls(self)
            dock.setWidget(panel)
            self.panels[name] = panel
            self.addDockWidget(Qt.RightDockWidgetArea, dock)
            self.docks.append(dock)
            prev = dock
        del prev
        self._tabify_panels()
        for dock in self.docks:
            self.window_menu.addAction(dock.toggleViewAction())
        self.window_menu.addAction(self.controlbar.toggleViewAction())

        sb = self.statusBar()
        self.tool_label = QLabel()
        self.coord_label = QLabel("X: –  Y: –")
        self.coord_label.setMinimumWidth(170)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        sb.addPermanentWidget(self.tool_label)
        sb.addPermanentWidget(self.coord_label)
        sb.addPermanentWidget(self.zoom_label)

        self.state.changed.connect(self.refresh_context)
        self.autosave = AutosaveManager(self)
        first = "select" if "select" in self.tools else self.tool_list[0].name
        self.set_tool(first)
        self._update_actions()

    def _tabify_panels(self) -> None:
        """Stack related panels as tabs so the right side stays compact."""
        by_name = {d.objectName(): d for d in self.docks}
        for a, b in (("panel_properties", "panel_align"), ("panel_color", "panel_stroke")):
            if a in by_name and b in by_name:
                self.tabifyDockWidget(by_name[a], by_name[b])
                by_name[a].raise_()

    # ==================================================================
    # Menus
    # ==================================================================
    def _act(self, menu, text, slot, shortcut=None, area=None, checkable=False, checked=False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            keys = shortcut if isinstance(shortcut, list) else [shortcut]
            a.setShortcuts([QKeySequence(k) for k in keys])
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda _=False: slot())
        menu.addAction(a)
        self.addAction(a)
        self.actions_by_area.append((area or menu.title().replace("&", ""), a))
        return a

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "New…", self.new_document_dialog, "Ctrl+N")
        self._act(m, "Open…", self.open_dialog, "Ctrl+O")
        self.recent_menu = m.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addSeparator()
        self.a_save = self._act(m, "Save", self.save, "Ctrl+S")
        self.a_save_as = self._act(m, "Save As…", self.save_as, "Ctrl+Shift+S")
        m.addSeparator()
        self.a_png = self._act(m, "Export PNG…", self.export_png_dialog, "Ctrl+Shift+E")
        self.a_pdf = self._act(m, "Export PDF…", self.export_pdf_dialog, "Ctrl+Shift+P")
        m.addSeparator()
        self.a_setup = self._act(m, "Document Setup…", self.document_setup, "Ctrl+Alt+P")
        self.a_close = self._act(m, "Close", lambda: self.close_tab(self.tab_widget.currentIndex()), "Ctrl+W")
        self._act(m, "Quit", self.close, "Ctrl+Q")

        m = mb.addMenu("&Edit")
        self.a_undo = self._act(m, "Undo", self.undo, "Ctrl+Z")
        self.a_redo = self._act(m, "Redo", self.redo, ["Ctrl+Shift+Z", "Ctrl+Y"])
        m.addSeparator()
        self._act(m, "Cut", self.cut, "Ctrl+X")
        self._act(m, "Copy", self.copy, "Ctrl+C")
        self._act(m, "Paste", self.paste, "Ctrl+V")
        self._act(m, "Paste in Place", lambda: self.paste(in_place=True), "Ctrl+Shift+V")
        self._act(m, "Duplicate", self.duplicate, "Ctrl+D")
        self._act(m, "Delete", self.delete_selection, ["Delete", "Backspace"])
        m.addSeparator()
        self._act(m, "Preferences…", self.preferences, "Ctrl+K")

        m = mb.addMenu("&Object")
        self._act(m, "Group", self.group, "Ctrl+G")
        self._act(m, "Ungroup", self.ungroup, "Ctrl+Shift+G")
        sub = m.addMenu("Arrange")
        self._act(sub, "Bring to Front", lambda: self.arrange("front"), "Ctrl+Shift+]", "Object")
        self._act(sub, "Bring Forward", lambda: self.arrange("forward"), "Ctrl+]", "Object")
        self._act(sub, "Send Backward", lambda: self.arrange("backward"), "Ctrl+[", "Object")
        self._act(sub, "Send to Back", lambda: self.arrange("back"), "Ctrl+Shift+[", "Object")
        m.addSeparator()
        self._act(m, "Lock Selection", lambda: self.set_flag("locked", True), "Ctrl+2")
        self._act(m, "Unlock All", lambda: self.set_flag_all("locked", False), "Ctrl+Alt+2")
        self._act(m, "Hide Selection", lambda: self.set_flag("visible", False), "Ctrl+3")
        self._act(m, "Show All", lambda: self.set_flag_all("visible", True), "Ctrl+Alt+3")
        m.addSeparator()
        sub = m.addMenu("Path")
        self._act(sub, "Union", lambda: self.boolean("union"), "Ctrl+Alt+U", "Object")
        self._act(sub, "Subtract Front", lambda: self.boolean("subtract"), "Ctrl+Alt+S", "Object")
        self._act(sub, "Intersect", lambda: self.boolean("intersect"), "Ctrl+Alt+I", "Object")
        self._act(sub, "Exclude", lambda: self.boolean("exclude"), "Ctrl+Alt+X", "Object")
        sub.addSeparator()
        self._act(sub, "Convert to Path", self.convert_to_path, "Ctrl+Shift+C", "Object")

        m = mb.addMenu("&Type")
        self._act(m, "Font…", self.choose_font, "Ctrl+T")
        self._act(m, "Bold", lambda: self.toggle_text_flag("bold"), "Ctrl+B")
        self._act(m, "Italic", lambda: self.toggle_text_flag("italic"), "Ctrl+I")
        m.addSeparator()
        self._act(m, "Create Outlines", self.create_outlines, "Ctrl+Shift+O")

        m = mb.addMenu("&Select")
        self._act(m, "All", self.select_all, "Ctrl+A")
        self._act(m, "Deselect", self.deselect, "Ctrl+Shift+A")
        self._act(m, "Inverse", self.select_inverse, "Ctrl+Shift+I")

        m = mb.addMenu("&View")
        self._act(m, "Zoom In", lambda: self.with_view(lambda v: v.zoom_in()), ["Ctrl++", "Ctrl+="])
        self._act(m, "Zoom Out", lambda: self.with_view(lambda v: v.zoom_out()), "Ctrl+-")
        self._act(m, "Fit Artboard in Window", lambda: self.with_view(lambda v: v.fit_artboard()), "Ctrl+0")
        self._act(m, "Actual Size", lambda: self.with_view(lambda v: v.actual_size()), "Ctrl+1")
        m.addSeparator()
        self.a_rulers = self._act(m, "Rulers", self.set_rulers, "Ctrl+R", checkable=True,
                                  checked=self.settings.get("show_rulers"))
        self.a_guides = self._act(m, "Show Guides", self.set_guides_visible, "Ctrl+;", checkable=True, checked=True)
        self.a_lock_guides = self._act(m, "Lock Guides", self.set_guides_locked, "Ctrl+Alt+;", checkable=True)
        self._act(m, "Clear Guides", self.clear_guides)
        m.addSeparator()
        sub = m.addMenu("Theme")
        grp = QActionGroup(self)
        for name in ("dark", "light"):
            a = QAction(name.capitalize(), self, checkable=True)
            a.setChecked(self.settings.get("theme") == name)
            a.triggered.connect(lambda _=False, n=name: self.set_theme(n))
            grp.addAction(a)
            sub.addAction(a)
        self.theme_actions = grp

        self.window_menu = mb.addMenu("&Window")

        m = mb.addMenu("&Help")
        self._act(m, "Keyboard Shortcuts…", self.show_shortcuts, "F1")
        self._act(m, f"About {APP_NAME}", self.about)

        # tool and swatch shortcuts
        for t in self.tool_list:
            a = QAction(t.label, self)
            keys = {"add_anchor": ["+", "="], "delete_anchor": ["-"]}.get(t.name, [t.shortcut] if t.shortcut else [])
            a.setShortcuts([QKeySequence(k) for k in keys])
            a.triggered.connect(lambda _=False, n=t.name: self.set_tool(n))
            self.addAction(a)
            self.actions_by_area.append(("Tools", a))
        for text, key, slot in (("Swap Fill and Stroke", "Shift+X", self.state.swap),
                                ("Default Fill and Stroke", "D", self.state.reset_default),
                                ("Toggle Fill / Stroke Target", "X", self.toggle_target),
                                ("Set Paint to None", "/", self.set_paint_none)):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, s=slot: s())
            self.addAction(a)
            self.actions_by_area.append(("Tools", a))

    # ==================================================================
    # Tabs / context
    # ==================================================================
    @property
    def tab(self) -> DocumentTab | None:
        w = self.tab_widget.currentWidget()
        return w if isinstance(w, DocumentTab) else None

    def tabs(self) -> list[DocumentTab]:
        return [self.tab_widget.widget(i) for i in range(self.tab_widget.count())]

    def with_view(self, fn) -> None:
        if self.tab:
            fn(self.tab.view)

    def selection(self) -> list[Item]:
        return list(self.tab.scene.selection) if self.tab else []

    def selection_leaves(self) -> list[Item]:
        return [leaf for it in self.selection() for leaf in it.leaves()]

    def selection_rect(self) -> QRectF | None:
        return self.tab.scene.selection_rect() if self.tab else None

    def refresh_context(self) -> None:
        """Schedule one refresh of panels / control bar."""
        self._ctx_timer.start(0)

    def status_message(self, text: str, ms: int = 4000) -> None:
        self.statusBar().showMessage(text, ms)

    def add_tab(self, doc: Document, path: str | None = None) -> DocumentTab:
        tab = DocumentTab(self, doc, path)
        tab.set_rulers_visible(self.a_rulers.isChecked())
        tab.view.guides_visible = self.a_guides.isChecked()
        tab.view.guides_locked = self.a_lock_guides.isChecked()
        tab.scene.pasteboard_color = QColor(theme.current()["pasteboard"])
        tab.view.zoomChanged.connect(lambda z, t=tab: self._zoom_changed(t, z))
        tab.view.cursorMoved.connect(self._cursor_moved)
        tab.scene.selectionChangedSignal.connect(self._selection_changed)
        tab.scene.documentChanged.connect(lambda _k: self.refresh_context())
        tab.stack.cleanChanged.connect(lambda _c, t=tab: self._update_tab_title(t))
        tab.stack.indexChanged.connect(lambda _i: self._update_actions())
        i = self.tab_widget.addTab(tab, tab.title())
        self.tab_widget.setCurrentIndex(i)
        QTimer.singleShot(0, tab.view.fit_artboard)
        return tab

    def _update_tab_title(self, tab: DocumentTab) -> None:
        i = self.tab_widget.indexOf(tab)
        if i >= 0:
            self.tab_widget.setTabText(i, tab.title())
            self.tab_widget.setTabToolTip(i, tab.path or tab.name())
        if tab is self.tab:
            self.setWindowTitle(f"{tab.title()} — {APP_NAME}")

    def _tab_changed(self, _index: int) -> None:
        for t in self.tabs():
            if t is not self.tab:
                t.view.set_tool(None)
        tab = self.tab
        if tab:
            tab.view.set_tool(self.tool)
            self._update_tab_title(tab)
            self._zoom_changed(tab, tab.view.zoom)
            tab.view.setFocus()
        else:
            self.setWindowTitle(APP_NAME)
        self._update_actions()
        self.refresh_context()

    def _zoom_changed(self, tab, z: float) -> None:
        if tab is self.tab:
            self.zoom_label.setText(f"{z * 100:.0f}%")

    def _cursor_moved(self, pos) -> None:
        self.coord_label.setText(f"X: {pos.x():.1f}  Y: {pos.y():.1f}")

    def _selection_changed(self) -> None:
        leaves = self.selection_leaves()
        if leaves:
            first = leaves[0]
            kw = dict(fill=first.fill, stroke=first.stroke, stroke_width=first.stroke_width)
            if isinstance(first, TextItem):
                kw.update(font_family=first.font_family, font_size=first.font_size)
            if isinstance(first, RectItem):
                kw.update(corner_radius=first.rx)
            self.state.set(**kw)
        self.refresh_context()

    def _update_actions(self) -> None:
        tab = self.tab
        for a in (self.a_save, self.a_save_as, self.a_png, self.a_pdf, self.a_setup, self.a_close):
            a.setEnabled(tab is not None)
        self.a_undo.setEnabled(tab is not None)
        self.a_redo.setEnabled(tab is not None and tab.stack.canRedo())
        self.a_undo.setText(f"Undo {tab.stack.undoText()}".strip() if tab else "Undo")
        self.a_redo.setText(f"Redo {tab.stack.redoText()}".strip() if tab else "Redo")

    # ==================================================================
    # Tools / paint state
    # ==================================================================
    def set_tool(self, name: str) -> None:
        tool = self.tools.get(name)
        if tool is None:
            return
        self.tool = tool
        if self.tab:
            self.tab.view.set_tool(tool)
        self.toolbox.set_active(name)
        self.tool_label.setText(f"{tool.label} Tool")
        self.refresh_context()

    def toggle_target(self) -> None:
        self.state.set(target="stroke" if self.state.target == "fill" else "fill")

    def set_paint_none(self) -> None:
        self.apply_style(self.state.target, None)

    def choose_color(self, target: str) -> None:
        self.state.set(target=target)
        cur = getattr(self.state, target)
        initial = qcolor(cur.first_color() if isinstance(cur, Gradient) else cur) if cur else QColor("#000000")
        col = QColorDialog.getColor(initial, self, f"{target.capitalize()} Color", QColorDialog.ShowAlphaChannel)
        if col.isValid():
            self.apply_style(target, from_qcolor(col))

    def begin_merge(self) -> str:
        """New merge key for one continuous slider drag."""
        self._merge_serial += 1
        return f"drag{self._merge_serial}"

    def apply_style(self, attr: str, value, text: str | None = None, merge_key: str | None = None) -> None:
        """Set a style attribute on the selection and as the default for new objects."""
        model_attr = "rx" if attr == "corner_radius" else attr
        if hasattr(self.state, attr):
            self.state.set(**{attr: value})
        tab = self.tab
        if not tab:
            return
        if attr == "opacity":
            targets = self.selection()
        elif attr in TEXT_ATTRS or attr == "text":
            targets = [i for i in self.selection_leaves() if isinstance(i, TextItem)]
        elif attr == "corner_radius":
            targets = [i for i in self.selection_leaves() if isinstance(i, RectItem)]
        else:
            targets = self.selection_leaves()
        changes = [(i, model_attr, value) for i in targets if getattr(i, model_attr) != value]
        if changes:
            tab.push(C.PropertyCommand(tab.doc, changes, text or f"Set {attr.replace('_', ' ').title()}", merge_key))

    def apply_geometry(self, x: float, y: float, w: float, h: float) -> None:
        tab, r = self.tab, self.selection_rect()
        if not tab or r is None:
            return
        sx = w / r.width() if r.width() > 1e-9 and w > 0 else 1.0
        sy = h / r.height() if r.height() > 1e-9 and h > 0 else 1.0
        m = Transform.translation(x, y).mul(Transform.scaling(sx, sy)).mul(Transform.translation(-r.x(), -r.y()))
        if not m.is_identity(1e-7):
            tab.push(C.transform_items(tab.doc, self.selection(), m, "Transform"))

    # ==================================================================
    # File
    # ==================================================================
    def startup(self, files: list[str]) -> None:
        self.recover_autosaves()
        for f in files:
            self.open_file(f)
        if not self.tabs():
            self.new_document()

    def new_document(self, width: float | None = None, height: float | None = None) -> DocumentTab:
        s = self.settings
        return self.add_tab(Document.new(width or s.get("default_width"), height or s.get("default_height")))

    def new_document_dialog(self) -> None:
        s = self.settings
        dlg = DocumentSizeDialog(self, "New Document", s.get("default_width"), s.get("default_height"))
        if dlg.exec():
            self.new_document(*dlg.size_values())

    def open_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Open", self._last_dir(), SVG_FILTER)
        for p in paths:
            self.open_file(p)

    def _last_dir(self) -> str:
        rec = self.settings.recent_files()
        return os.path.dirname(rec[0]) if rec else os.path.expanduser("~")

    def open_file(self, path: str) -> DocumentTab | None:
        path = os.path.abspath(path)
        for i, t in enumerate(self.tabs()):
            if t.path == path:
                self.tab_widget.setCurrentIndex(i)
                return t
        try:
            doc = svgio.load(path)
        except Exception as e:  # malformed XML, unreadable file, ...
            self.error(f"Could not open {os.path.basename(path)}:\n{e}")
            return None
        tab = self.add_tab(doc, path)
        self.settings.add_recent(path)
        skipped = getattr(doc, "import_skipped", 0)
        if skipped:
            self.status_message(f"{skipped} unsupported element(s) were skipped on import.", 8000)
        return tab

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        files = self.settings.recent_files()
        for p in files:
            a = self.recent_menu.addAction(os.path.basename(p))
            a.setToolTip(p)
            a.setEnabled(os.path.exists(p))
            a.triggered.connect(lambda _=False, f=p: self.open_file(f))
        if files:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction("Clear Recent Files").triggered.connect(self.settings.clear_recent)
        else:
            self.recent_menu.addAction("No Recent Files").setEnabled(False)

    def save(self, tab: DocumentTab | None = None) -> bool:
        tab = tab or self.tab
        if not tab:
            return False
        if not tab.path:
            return self.save_as(tab)
        return self._write(tab, tab.path)

    def save_as(self, tab: DocumentTab | None = None, path: str | None = None) -> bool:
        tab = tab or self.tab
        if not tab:
            return False
        if path is None:
            start = tab.path or os.path.join(self._last_dir(), tab.name() + ".svg")
            path, _ = QFileDialog.getSaveFileName(self, "Save As", start, SVG_FILTER)
            if not path:
                return False
            if not os.path.splitext(path)[1]:
                path += ".svg"
        return self._write(tab, path)

    def _write(self, tab: DocumentTab, path: str) -> bool:
        if tab.text_editor is not None:
            tab.text_editor.commit()
        try:
            svgio.save(tab.doc, path)
        except OSError as e:
            self.error(f"Could not save:\n{e}")
            return False
        tab.path = os.path.abspath(path)
        tab.force_dirty = False
        tab.stack.setClean()
        self.autosave.discard(tab)
        self.settings.add_recent(tab.path)
        self._update_tab_title(tab)
        self.status_message(f"Saved {tab.path}")
        return True

    def export_png_dialog(self) -> None:
        tab = self.tab
        if not tab:
            return
        dlg = ExportDialog(self, "PNG", tab.doc.width, tab.doc.height)
        if not dlg.exec():
            return
        base = os.path.splitext(tab.path or os.path.join(self._last_dir(), tab.name()))[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", base + ".png", "PNG image (*.png)")
        if path:
            ok = export_png(tab.doc, path, dlg.scale.value(), dlg.transparent.isChecked())
            self.status_message(f"Exported {path}" if ok else "PNG export failed")

    def export_pdf_dialog(self) -> None:
        tab = self.tab
        if not tab:
            return
        dlg = ExportDialog(self, "PDF", tab.doc.width, tab.doc.height)
        if not dlg.exec():
            return
        base = os.path.splitext(tab.path or os.path.join(self._last_dir(), tab.name()))[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", base + ".pdf", "PDF document (*.pdf)")
        if path:
            ok = export_pdf(tab.doc, path, dlg.scale.value())
            self.status_message(f"Exported {path}" if ok else "PDF export failed")

    def document_setup(self) -> None:
        tab = self.tab
        if not tab:
            return
        dlg = DocumentSizeDialog(self, "Document Setup", tab.doc.width, tab.doc.height)
        if dlg.exec():
            w, h = dlg.size_values()
            tab.push(C.PropertyCommand(tab.doc, [(tab.doc, "width", w), (tab.doc, "height", h)], "Document Setup"))
            tab.view.fit_artboard()

    def error(self, text: str) -> None:
        if self.interactive:
            QMessageBox.warning(self, APP_NAME, text)
        else:
            self.status_message(text)

    def _confirm_close(self, tab: DocumentTab) -> bool:
        if not tab.is_modified() or not self.interactive:
            return True
        r = QMessageBox.question(self, APP_NAME, f"Save changes to {tab.name()}?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save(tab)
        return r == QMessageBox.Discard

    def close_tab(self, index: int) -> bool:
        tab = self.tab_widget.widget(index)
        if not isinstance(tab, DocumentTab) or not self._confirm_close(tab):
            return False
        tab.view.set_tool(None)
        tab.view.blockSignals(True)  # no late signals while Qt tears the tab down
        tab.stack.blockSignals(True)
        self.autosave.discard(tab)
        self.tab_widget.removeTab(index)
        tab.deleteLater()
        return True

    def closeEvent(self, ev) -> None:
        for i in range(self.tab_widget.count() - 1, -1, -1):
            if not self.close_tab(i):
                ev.ignore()
                return
        ev.accept()

    def recover_autosaves(self) -> int:
        pending = AutosaveManager.pending()
        if not pending:
            return 0
        if self.interactive:
            names = "\n".join(f"  • {e.get('name', 'Untitled')}" for e in pending)
            r = QMessageBox.question(self, APP_NAME,
                                     f"{APP_NAME} did not shut down cleanly. Recover these documents?\n{names}",
                                     QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                for e in pending:
                    AutosaveManager.remove_pending(e)
                return 0
        n = 0
        for e in pending:
            try:
                doc = svgio.load(e["svg"])
            except Exception:
                continue
            tab = self.add_tab(doc, e.get("path"))
            tab.force_dirty = True
            tab.autosave_dirty = True
            if not e.get("path"):
                tab.untitled_name = f"{e.get('name', 'Untitled')} (recovered)"
            self._update_tab_title(tab)
            AutosaveManager.remove_pending(e)
            n += 1
        return n

    # ==================================================================
    # Edit
    # ==================================================================
    def undo(self) -> None:
        tab = self.tab
        if not tab:
            return
        if self.tool and self.tool.undo_step(tab.view):
            tab.view.refresh()
            return
        tab.stack.undo()

    def redo(self) -> None:
        if self.tab:
            self.tab.stack.redo()

    def delete_selection(self) -> None:
        tab = self.tab
        if not tab:
            return
        if self.tool and self.tool.delete_pressed(tab.view):
            tab.view.refresh()
            return
        sel = self.selection()
        if sel:
            tab.push(C.delete_items(tab.doc, sel))

    def copy(self) -> None:
        tab = self.tab
        sel = ops.doc_order(tab.doc, ops.top_level_only(self.selection())) if tab else []
        if not sel:
            return
        self.clipboard = []
        for it in sel:
            c = it.clone()
            c.transform = it.world_transform()
            self.clipboard.append(c)
        self.paste_count = 0
        tmp = Document.new(tab.doc.width, tab.doc.height)
        for c in self.clipboard:
            tmp.add(c.clone())
        QGuiApplication.clipboard().setText(svgio.dumps(tmp))

    def cut(self) -> None:
        self.copy()
        if self.tab and self.selection():
            self.tab.push(C.delete_items(self.tab.doc, self.selection(), "Cut"))

    def _insert_layer(self, tab):
        layer = tab.scene.active_layer
        if layer is None or not layer.editable():
            self.status_message("The active layer is locked or hidden.")
            return None
        return layer

    def paste(self, in_place: bool = False) -> None:
        tab = self.tab
        if not tab:
            return
        items = [c.clone() for c in self.clipboard]
        if not items:
            text = QGuiApplication.clipboard().text()
            if "<svg" in text:
                try:
                    items = [it for it in svgio.loads(text).top_items()]
                except Exception:
                    items = []
        layer = self._insert_layer(tab)
        if not items or layer is None:
            return
        self.paste_count += 1
        off = 0 if in_place else 10 * self.paste_count
        for it in items:
            it.transform = Transform.translation(off, off).mul(it.transform)
        tab.push(C.add_items(tab.doc, layer, items, "Paste"))
        tab.scene.set_selection(items)

    def duplicate(self) -> None:
        tab = self.tab
        sel = ops.doc_order(tab.doc, ops.top_level_only(self.selection())) if tab else []
        if not sel:
            return
        cmds, clones = [], []
        for it in sel:
            c = it.clone()
            c.parent = it.parent  # so apply_world sees the same ancestors
            c.transform = ops.apply_world(c, Transform.translation(10, 10))
            clones.append(c)
        by_parent: dict[int, list] = {}
        for it, c in zip(sel, clones):
            by_parent.setdefault(id(it.parent), [it.parent, []])[1].append(c)
        for par, new in by_parent.values():
            cmds.append(C.add_items(tab.doc, par, new))
        tab.push(C.Macro("Duplicate", cmds))
        tab.scene.set_selection(clones)

    def preferences(self) -> None:
        dlg = PreferencesDialog(self, self.settings)
        if dlg.exec():
            dlg.apply()
            self.autosave.configure()
            self.set_theme(self.settings.get("theme"))

    # ==================================================================
    # Object
    # ==================================================================
    def group(self) -> None:
        tab = self.tab
        if not tab or len(self.selection()) < 1:
            return
        cmd, g = C.group_items(tab.doc, self.selection())
        if cmd:
            tab.push(cmd)
            tab.scene.set_selection([g])

    def ungroup(self) -> None:
        tab = self.tab
        if not tab:
            return
        groups = [i for i in self.selection() if isinstance(i, GroupItem)]
        others = [i for i in self.selection() if not isinstance(i, GroupItem)]
        cmd, children = C.ungroup_items(tab.doc, groups)
        if cmd:
            tab.push(cmd)
            tab.scene.set_selection(others + children)

    def arrange(self, how: str) -> None:
        tab = self.tab
        if tab and self.selection():
            tab.push(C.arrange_items(tab.doc, self.selection(), how))

    def set_flag(self, attr: str, value: bool) -> None:
        tab = self.tab
        if tab and self.selection():
            text = {("locked", True): "Lock", ("visible", False): "Hide"}.get((attr, value), "Change")
            sel = self.selection()
            tab.scene.set_selection([])
            tab.push(C.PropertyCommand(tab.doc, [(i, attr, value) for i in sel], text))

    def set_flag_all(self, attr: str, value: bool) -> None:
        tab = self.tab
        if not tab:
            return
        changes = [(i, attr, value) for i in tab.doc.all_items() if getattr(i, attr) != value]
        if changes:
            tab.push(C.PropertyCommand(tab.doc, changes, "Unlock All" if attr == "locked" else "Show All"))

    def _replace_cmds(self, tab, items, text: str):
        cmds, new = [], []
        for it in items:
            p = it.to_path_item()
            if p.path.is_empty():
                continue
            cmds.append(C.replace_item(tab.doc, it, p))
            new.append((it, p))
        return (C.Macro(text, cmds) if cmds else None), new

    def _convert(self, pred, text: str) -> None:
        tab = self.tab
        if not tab:
            return
        targets = [i for i in self.selection_leaves() if pred(i)]
        cmd, pairs = self._replace_cmds(tab, targets, text)
        if cmd:
            mapping = {id(old): new for old, new in pairs}
            sel = [mapping.get(id(i), i) for i in self.selection()]
            tab.push(cmd)
            tab.scene.set_selection(sel)

    def convert_to_path(self) -> None:
        self._convert(lambda i: not isinstance(i, (PathItem, GroupItem)), "Convert to Path")

    def create_outlines(self) -> None:
        self._convert(lambda i: isinstance(i, TextItem), "Create Outlines")

    def boolean(self, op: str) -> None:
        tab = self.tab
        sel = ops.doc_order(tab.doc, ops.top_level_only(self.selection())) if tab else []
        if len(sel) < 2:
            self.status_message("Select two or more objects for path operations.")
            return
        paths = []
        for it in sel:
            merged = PathItem().path
            for leaf in it.leaves():
                merged.subpaths += leaf.world_path().subpaths
            paths.append(merged)
        result = boolean_op(paths, op)
        style_src = next(iter((sel[0] if op == "subtract" else sel[-1]).leaves()), None)
        top = sel[-1]
        changes = dict((id(par), (par, ch)) for par, ch in ops.remove_items(sel))
        new_item = None
        if not result.is_empty() and style_src is not None:
            new_item = PathItem(path=result)
            for a in ("fill", "stroke", "stroke_width", "stroke_cap", "stroke_join", "dash"):
                setattr(new_item, a, getattr(style_src, a))
            inv = top.parent_world().inverted()
            new_item.transform = inv
            par, ch = changes[id(top.parent)]
            before = top.parent.children[: top.parent.children.index(top)]
            idx = sum(1 for c in before if c in ch)
            ch.insert(idx, new_item)
        tab.push(C.StructureCommand(tab.doc, list(changes.values()), f"Path {op.capitalize()}"))
        tab.scene.set_selection([new_item] if new_item else [])
        if new_item is None:
            self.status_message("The result of the path operation is empty.")

    # ==================================================================
    # Type
    # ==================================================================
    def choose_font(self) -> None:
        font, _ = make_font(self.state.font_family, self.state.font_size)
        ok, f = QFontDialog.getFont(font, self, "Font")
        if ok:
            tab = self.tab
            if tab:
                tab.stack.beginMacro("Font")
            self.apply_style("font_family", f.family())
            size = f.pixelSize() if f.pixelSize() > 0 else f.pointSizeF() * 96 / 72
            self.apply_style("font_size", float(size))
            if tab:
                tab.stack.endMacro()

    def toggle_text_flag(self, attr: str) -> None:
        texts = [i for i in self.selection_leaves() if isinstance(i, TextItem)]
        if texts and self.tab:
            value = not getattr(texts[0], attr)
            self.tab.push(C.PropertyCommand(self.tab.doc, [(t, attr, value) for t in texts], attr.capitalize()))

    # ==================================================================
    # Select
    # ==================================================================
    def select_all(self) -> None:
        if self.tab:
            self.tab.scene.set_selection(self.tab.scene.selectable_items())

    def deselect(self) -> None:
        if self.tab:
            self.tab.scene.set_selection([])

    def select_inverse(self) -> None:
        if self.tab:
            cur = {id(i) for i in self.selection()}
            self.tab.scene.set_selection([i for i in self.tab.scene.selectable_items() if id(i) not in cur])

    # ==================================================================
    # View
    # ==================================================================
    def set_rulers(self, on: bool) -> None:
        self.settings.set("show_rulers", on)
        for t in self.tabs():
            t.set_rulers_visible(on)

    def set_guides_visible(self, on: bool) -> None:
        for t in self.tabs():
            t.view.guides_visible = on
            t.view.refresh()

    def set_guides_locked(self, on: bool) -> None:
        for t in self.tabs():
            t.view.guides_locked = on

    def clear_guides(self) -> None:
        tab = self.tab
        if tab and tab.doc.guides:
            tab.push(C.PropertyCommand(tab.doc, [(tab.doc, "guides", ())], "Clear Guides"))

    def set_theme(self, name: str) -> None:
        self.settings.set("theme", name)
        theme.apply_theme(QApplication.instance(), name)
        for a in self.theme_actions.actions():
            a.setChecked(a.text().lower() == name)
        for t in self.tabs():
            t.scene.pasteboard_color = QColor(theme.current()["pasteboard"])
            t.scene.update()
            t.hruler.update()
            t.vruler.update()
        self.toolbox.retheme()
        for p in self.panels.values():
            if hasattr(p, "retheme"):
                p.retheme()
        self.refresh_context()

    # ==================================================================
    # Help
    # ==================================================================
    def shortcut_rows(self) -> list[tuple[str, str, str]]:
        rows = []
        for area, a in self.actions_by_area:
            keys = ", ".join(k.toString(QKeySequence.NativeText) for k in a.shortcuts())
            if keys:
                rows.append((area, a.text().replace("&", "").rstrip("…"), keys))
        return rows + EXTRA_SHORTCUTS

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self, self.shortcut_rows()).exec()

    def about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setTextFormat(Qt.RichText)
        box.setText(ABOUT_HTML)
        box.setIconPixmap(QIcon(self.windowIcon()).pixmap(96, 96))
        box.exec()
